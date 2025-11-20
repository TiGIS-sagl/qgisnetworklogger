# -*- coding: utf-8 -*-
# Import the PyQt and QGIS libraries
from logging.handlers import RotatingFileHandler
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

from qgis.PyQt.QtNetwork import QNetworkAccessManager, QNetworkRequest
from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox, QAction
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

        self.handler = RotatingFileHandler(
            self.filePath, maxBytes=1 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        self.handler.setFormatter(
            logging.Formatter("%(asctime)s \t %(message)s", "%Y-%m-%d %H:%M:%S")
        )

        self.logger = logging.getLogger("QgisNetworkLogger")
        self.logger.setLevel(logging.INFO)
        self.logger.addHandler(self.handler)

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
        self.logger.removeHandler(self.handler)
        self.handler.close()

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

    def writeLog(self, event, requestId, op, url, status, details):
        """
        Log the messagge in the file as TSV or the messagelog. Doesn't handle none values, provide
        empty string instead

        :param details: string can be any addition detail to the call
        """
        if self.showMessageLog:
            QgsMessageLog.logMessage(
                f"{event}: {op or status} - {url}", "QGIS Network Logger...", Qgis.MessageLevel.Info
            )
        self.logger.info(
            "\t".join([event, str(requestId), op, url, str(status), " ".join(details.split())])
        )

    def request_about_to_be_created(self, request):
        """
        :type request: QgsNetworkRequestParameters
        """
        op = self.operation2string(request.operation())
        url = request.request().url().toString()
        data = request.content().data().decode("utf-8", errors="replace")
        self.writeLog("Requesting", request.requestId(), op, url, "-", data)

    def request_timed_out(self, request):
        """
        :param request: QgsNetworkRequestParameters
        """
        url = request.request().url().toString()
        op = self.operation2string(request.operation())
        self.writeLog("Timeout or abort", request.requestId(), op, url, "-", "")

    def request_finished(self, reply):
        """
        :type reply: QgsNetworkReplyContent
        """
        url = reply.request().url().toString()
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        length = reply.attribute(QNetworkRequest.Attribute.OriginalContentLengthAttribute)
        self.writeLog(
            "Finished", reply.requestId(), "-", url, status, f"Lenght: {length}" if length else ""
        )

    def operation2string(self, operation):
        """
        Create http-operation String from Operation

        :type operation: QNetworkAccessManager.Operation
        :retrun: string
        """
        match operation:
            case QNetworkAccessManager.Operation.HeadOperation:
                return "HEAD"
            case QNetworkAccessManager.Operation.GetOperation:
                return "GET"
            case QNetworkAccessManager.Operation.PutOperation:
                return "PUT"
            case QNetworkAccessManager.Operation.PostOperation:
                return "POST"
            case QNetworkAccessManager.Operation.DeleteOperation:
                return "DELETE"
            case QNetworkAccessManager.Operation.CustomOperation:
                return "Custom"
