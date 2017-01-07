#Import python modules
import sys, os, re, shutil, random
import subprocess

import logging
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

#Import GUI
from PySide import QtCore
from PySide import QtGui

from shiboken import wrapInstance

#Import maya commands
import maya.cmds as mc
import maya.mel as mm
from functools import partial

# import ui
import ui
from rftool.utils import file_utils
from rftool.utils import path_info
from rftool.utils import sg_wrapper
from rftool.utils import sg_process
from rftool.utils import icon
from rftool.utils import pipeline_utils
from rftool.utils import maya_utils
from startup import config
from rftool.utils.userCheck import user_app

moduleDir = sys.modules[__name__].__file__


# If inside Maya open Maya GUI
def getMayaWindow():
    ptr = mui.MQtUtil.mainWindow()
    return wrapInstance(long(ptr), QtGui.QWidget)
    # return sip.wrapinstance(long(ptr), QObject)

import maya.OpenMayaUI as mui

def show(pathInfo, entity):
    uiName = 'PropItUI'
    deleteUI(uiName)
    myApp = PropIt(pathInfo, entity, getMayaWindow())
    myApp.show()

def deleteUI(ui):
    if mc.window(ui, exists=True):
        mc.deleteUI(ui)
        deleteUI(ui)

class PropIt(QtGui.QMainWindow):

    def __init__(self, pathInfo, entity, parent=None):
        self.count = 0
        #Setup Window
        super(PropIt, self).__init__(parent)
        self.ui = ui.Ui_PropItUI()
        self.ui.setupUi(self)

        self.asset = pathInfo
        self.entity = entity
        self.res = ['md', 'lo', 'hi']
        self.cam = 'propIt_cam'
        self.tempGrp = 'tmpMove_grp'
        self.objectLoc = 'tmpObj_loc'
        self.centerLoc = 'tmpCenter_loc'
        self.rigGrp = 'Rig_Grp'
        self.placeCtrl = 'Place_Ctrl'
        self.currentCam = None

        self.setWindowTitle('Prop It v.0.0.1')

        self.originMatrix = None

        self.set_info()
        self.init_signals()


    def set_info(self):
        self.ui.project_label.setText(self.asset.project)
        self.ui.type_label.setText(self.asset.type)
        self.ui.subtype_label.setText(self.asset.subtype)
        self.ui.asset_label.setText(self.asset.name)
        self.ui.id_label.setText(str(self.entity.get('id')))
        self.ui.res_comboBox.addItems(self.res)

    def init_signals(self):
        self.ui.center_pushButton.clicked.connect(self.set_center)
        self.ui.createRig_pushButton.clicked.connect(self.rig)
        self.ui.export_pushButton.clicked.connect(self.export)
        self.ui.propCam_pushButton.clicked.connect(self.set_propCam)
        self.ui.currentCam_pushButton.clicked.connect(self.set_currentCam)
        self.ui.duplicateReference_pushButton.clicked.connect(self.duplicate_ref)


    def set_center(self):
        selObjs = mc.ls(sl=True)
        result = True

        # center obj
        if selObjs:
            result = self.center_objects(selObjs)
            mc.select(selObjs)

        if result:
            # set camera
            self.create_cam()

    def create_cam(self):
        panel = mc.getPanel(withFocus=True)
        if mc.getPanel(to=panel) == 'modelPanel':
            self.currentCam = mc.modelPanel(panel, q=True, cam=True)
            self.ui.currentCam_pushButton.setText(self.currentCam)
            print self.currentCam

            if not mc.objExists(self.cam):
                cam = mc.camera(centerOfInterest=5)[0]
                propCam = mc.rename(cam, self.cam)
                self.ui.propCam_pushButton.setText(propCam)

            mc.lookThru(self.cam, panel)
            mc.viewFit(f=0.5)

        else:
            QtGui.QMessageBox.information(self, 'Information', 'Please focus on the viewport')

    def center_objects(self, objs):
        if all(not mc.referenceQuery(a, inr=True) for a in objs):
            # group objs to move back to center
            self.tempGrp = mc.group(objs, n=self.tempGrp)

            self.objectLoc = mc.spaceLocator(n=self.objectLoc)
            mc.delete(mc.parentConstraint(self.tempGrp, self.objectLoc))
            mc.delete(mc.scaleConstraint(self.tempGrp, self.objectLoc))

            # get current matrix
            self.originMatrix = mc.xform(self.objectLoc, q=True, ws=True, m=True)
            mc.delete(self.objectLoc)

            # get back to center
            loc = mc.spaceLocator(n=self.centerLoc)

            # delete reference objects
            mc.delete(mc.pointConstraint(loc, self.tempGrp))
            mc.delete(loc)
            mc.parent(objs, w=True)
            mc.delete(self.tempGrp)

            return True

        else:
            QtGui.QMessageBox.information(self, 'Warning', 'One or more selected objects are reference node')
            return False

    def rig(self):
        objs = mc.ls(sl=True)
        res = str(self.ui.res_comboBox.currentText())
        if objs:
            if not mc.objExists(self.rigGrp):
                rigGrp = maya_utils.create_rig_grp(objs=objs, res=res, ctrl=True)
            else:
                QtGui.QMessageBox.warning(self, 'Warning', '%s exists in the scene. cannot Export' % self.rigGrp)


        else:
            QtGui.QMessageBox.information(self, 'Warning', 'Please select objects to rig')

    def export(self):
        res = str(self.ui.res_comboBox.currentText())
        refPath = self.asset.libPath()
        rigName = self.asset.libName(step='rig', res=res)
        exportPath = '%s/%s' % (refPath, rigName)
        exportResult = None
        sgResult = None

        if not os.path.exists(refPath):
            os.makedirs(refPath)
            logger.debug('Create lib dir')

        if mc.objExists(self.rigGrp):
            mc.select(self.rigGrp)
            mc.file(exportPath, f=True, es=True, type='mayaAscii')
            logger.info('Export success %s' % exportPath)

            if os.path.exists(exportPath):
                exportResult = True

                try:
                    self.set_shotgun_status()
                    sgResult = True
                except Exception as e:
                    logger.error(e)

        else:
            QtGui.QMessageBox.warning(self, 'Warning', '%s not exists. Cannot export' % self.rigGrp)

        if not sgResult:
            logger.warning('Failed to update shotgun status')
            QtGui.QMessageBox.warning(self, 'Error', 'Failed to update Shotgun status')

        if exportResult:
            logger.info('Successfully export %s' % exportResult)
            QtGui.QMessageBox.information(self, 'Success', 'Export success')

            if self.ui.deleteProxy_checkBox.isChecked():
                mc.delete(self.rigGrp)

            # create ref
            if self.ui.ref_checkBox.isChecked():
                namespace = maya_utils.create_reference('%s_%s' % (self.asset.name, res), exportPath)
                # mc.delete(self.rigGrp)

                # restore position
                self.restore_position(namespace)

                # restore camera
                self.restore_camera()

        else:
            logger.warning('Failed to export')
            QtGui.QMessageBox.warning(self, 'Error', 'Failed to export rig')



    def restore_position(self, namespace):
        if self.originMatrix:
            moveCtrl = '%s:%s' % (namespace, self.placeCtrl)
            if mc.objExists(moveCtrl):
                mc.xform(moveCtrl, m=self.originMatrix)

    def restore_camera(self):
        panel = mc.getPanel(withFocus=True)
        if mc.getPanel(to=panel) == 'modelPanel':
            if self.currentCam:
                mc.lookThru(self.currentCam, panel)
                mc.delete(self.cam)

    def set_propCam(self):
        panel = mc.getPanel(withFocus=True)
        if mc.getPanel(to=panel) == 'modelPanel':
            mc.lookThru(self.cam, panel)

    def set_currentCam(self):
        panel = mc.getPanel(withFocus=True)
        if mc.getPanel(to=panel) == 'modelPanel':
            if self.currentCam:
                mc.lookThru(self.currentCam, panel)

    def set_shotgun_status(self):
        logger.info('set shotgun status')
        res = str(self.ui.res_comboBox.currentText())
        tasks = sg_process.get_tasks(self.entity)
        status = 'pxy'

        if tasks:
            # set rig task status
            rigTask = 'rig_%s' % (res)
            rigTaskId = [a['id'] for a in tasks if a['content'] == rigTask][0]
            result1 = sg_process.set_task_status(rigTaskId, status)

            # set asset status
            entity = 'Asset'
            result2 = sg_process.set_entity_status(entity, self.entity.get('id'), status)

            # set model ready to start
            status = 'rdy'
            modelTask = 'model_%s' % (res)
            modelTaskId = [a['id'] for a in tasks if a['content'] == modelTask][0]
            result3 = sg_process.set_task_status(modelTaskId, status)


    def duplicate_ref(self):
        obj = mc.ls(sl=True)

        if obj:
            matrix = mc.xform(obj[0], q=True, ws=True, m=True)
            path = mc.referenceQuery(obj[0], f=True)
            namespace = maya_utils.duplicate_reference(path)
            moveCtrl = '%s:%s' % (namespace, self.placeCtrl)

            if mc.objExists(moveCtrl):
                mc.select(moveCtrl)
                mc.xform(moveCtrl, m=matrix)
