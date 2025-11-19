# -*- coding: utf-8 -*-
# Import the PyQt and QGIS libraries
import logging
import os

from qgis.core import (
    QgsNetworkRequestParameters,
    QgsExpressionContextUtils,
    QgsNetworkAccessManager,
    QgsNetworkReplyContent,
    QgsMessageLog,
    Qgis,
)

from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox, QAction
from qgis.PyQt.QtNetwork import QNetworkRequest
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon


class QgisNetworkLogger:
    """
    Log all the http request into a file using python logging
    """

    def __init__(self, iface):
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.action = None

        self.showMessageLog = False

        nam = QgsNetworkAccessManager.instance()
        assert nam is not None, "QgisNetworkLogger cannot access the newtwork access manager"
        self.nam = nam

        self.nam.requestAboutToBeCreated[QgsNetworkRequestParameters].connect(
            self.request_about_to_be_created
        )
        self.nam.requestTimedOut[QgsNetworkRequestParameters].connect(self.request_timed_out)
        self.nam.finished[QgsNetworkReplyContent].connect(self.request_finished)

        variableName = "network_log_file"

        def getLogFilePath():
            filePath, _ = QFileDialog.getSaveFileName(
                self.iface.mainWindow(),
                "Select log file",
                "",
                "Log Files (*.log);;All Files (*)",
            )
            return filePath

        globalScope = QgsExpressionContextUtils.globalScope()

        if globalScope:
            if globalScope.hasVariable(variableName):
                self.filePath = globalScope.variable(variableName)
            else:
                self.filePath = getLogFilePath()
                QgsExpressionContextUtils.setGlobalVariable(variableName, self.filePath)
        else:
            self.filePath = getLogFilePath()

        logging.basicConfig(
            filename=self.filePath,
            level=logging.INFO,
            format="%(asctime)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    def initGui(self):
        self.action = QAction(
            QIcon(os.path.dirname(__file__) + "/icons/icon.png"),
            "&QGIS Network Logger",
            self.iface.mainWindow(),
        )
        self.action.triggered.connect(self.show_dialog)

        self.iface.addPluginToMenu("QGIS Network Logger", self.action)

    def unload(self):
        """
        Disconnect signals and remove the plugin on close
        """
        if self.action:
            self.iface.removePluginMenu("QGIS Network Logger", self.action)

        self.nam.requestAboutToBeCreated[QgsNetworkRequestParameters].disconnect(
            self.request_about_to_be_created
        )
        self.nam.requestTimedOut[QgsNetworkRequestParameters].disconnect(self.request_timed_out)
        self.nam.finished[QgsNetworkReplyContent].disconnect(self.request_finished)

    def show_dialog(self):
        """
        The dialog of the menu bar
        """
        reply = QMessageBox.question(
            self.iface.mainWindow(),
            QCoreApplication.translate("QGISNetworkLogger", "QGIS Network Logger"),
            QCoreApplication.translate(
                "QGISNetworkLogger",
                f"Log file {self.filePath}\n\n" "Press yes to enable log messages, no to disable.",
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        self.showMessageLog = reply == QMessageBox.StandardButton.Yes
        return

    def show(self, msg):
        """
        Log the messagge in the file or the messagelog

        :param msg: string
        """
        if self.showMessageLog:
            QgsMessageLog.logMessage(msg, "QGIS Network Logger...", Qgis.MessageLevel.Info)
        logging.info(msg)

    def request_about_to_be_created(self, request):
        """
        :param request: QgsNetworkRequestParameters
        """
        op = self.operation2string(request.operation())
        url = request.request().url().toString()
        rawData = bytes(request.content())
        data = rawData.decode("utf-8", errors="replace")
        self.show(f"Requesting: {op} {url}")
        if len(rawData):
            self.show(f"Request data: {data}")

    def request_timed_out(self, request):
        """
        :param request: QgsNetworkRequestParameters
        """
        url = request.request().url().toString()
        op = self.operation2string(request.operation())
        self.show(f"Timeout or abort: {op} - {url}")

    def request_finished(self, reply):
        """
        :param reply: QgsNetworkReplyContent
        """
        url = reply.request().url().toString()
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        length = reply.attribute(QNetworkRequest.Attribute.OriginalContentLengthAttribute)
        self.show(f"Finished: {status} - {url}")
        if length is not None:
            self.show(f"- Length {length}")

    def operation2string(self, operation):
        """
        Create http-operation String from Operation

        :param operation: QNetworkAccessManager.Operation
        :retrun: string
        """
        match operation:
            case 1:
                return "HEAD"
            case 2:
                return "GET"
            case 3:
                return "PUT"
            case 4:
                return "POST"
            case 5:
                return "DELETE"
            case _:
                return "Custom"
