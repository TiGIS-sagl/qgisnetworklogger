# -*- coding: utf-8 -*-
"""
Main plugin entry point for the QGIS Network Logger plugin.

This module hooks into the QGIS network access manager, captures HTTP
request/response metadata, and forwards it to the background worker
process for structured logging.
"""
from logging.handlers import RotatingFileHandler
import logging
import subprocess
import json
import sys
import os

from qgis.core import (
    QgsNetworkRequestParameters,
    QgsExpressionContextUtils,
    QgsNetworkAccessManager,
    QgsNetworkReplyContent,
    QgsMessageLog,
    Qgis,
)

from qgis.PyQt.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
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

        self.logger = logging.getLogger("QgisNetworkLoggerClient")
        self.logger.setLevel(logging.INFO)
        self._fallback_handler = None
        self._logger_process = None
        self._logger_stream = None
        self._start_logger_process()

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
        self._shutdown_logger_process()
        self._teardown_fallback_handler()

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

    def writeLog(self, event, requestId, op, url, status, details, headers):
        """
        Log the messagge in the file as TSV or the messagelog. Doesn't handle none values, provide
        empty string instead

        :param details: string can be any addition detail to the call
        """
        if self.showMessageLog:
            QgsMessageLog.logMessage(
                f"{event}: {op or status} - {url}", "QGIS Network Logger...", Qgis.MessageLevel.Info
            )
        payload = {
            "event": event,
            "request_id": requestId,
            "operation": op,
            "url": url,
            "status": status,
            "details": " ".join(details.split()),
            "headers": headers,
        }
        if not self._send_to_worker(payload):
            self._fallback_log(payload)

    def request_about_to_be_created(self, request):
        """
        :type request: QgsNetworkRequestParameters
        """
        op = self.operation2string(request.operation())
        url = request.request().url().toString()
        data = request.content().data().decode("utf-8", errors="replace")
        headers = self.rawHeader2string(request.request(), request.request().rawHeaderList())
        self.writeLog("Requesting", request.requestId(), op, url, "-", data, headers)

    def request_timed_out(self, request):
        """
        :param request: QgsNetworkRequestParameters
        """
        url = request.request().url().toString()
        op = self.operation2string(request.operation())
        headers = self.rawHeader2string(request.request(), request.request().rawHeaderList())
        self.writeLog("Timeout or abort", request.requestId(), op, url, "-", "", headers)

    def request_finished(self, reply):
        """
        :type reply: QgsNetworkReplyContent
        """
        url = reply.request().url().toString()
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        length = reply.attribute(QNetworkRequest.Attribute.OriginalContentLengthAttribute)
        headers = self.rawHeader2string(reply.request(), reply.request().rawHeaderList())
        detail = (
            reply.errorString()
            if reply.error() != QNetworkReply.NetworkError.NoError
            else (f"Lenght: {length}" if length else "")
        )
        self.writeLog(
            "Finished",
            reply.requestId(),
            "-",
            url,
            status,
            detail,
            headers,
        )

    def operation2string(self, operation):
        """
        Create http-operation String from Operation

        :type operation: QNetworkAccessManager.Operation
        :return: string
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

    def rawHeader2string(self, request, rawHeaderList):
        """
        Convert the raw header list in to a string where each header is separated by a pipe.

        :type request: QNetworkRequest
        :type rawHeaderList: List[QByteArray]
        :return: string
        """
        return " | ".join(
            f'{h.data().decode("utf-8", errors="replace")}: '
            f'{request.rawHeader(h).data().decode("utf-8", errors="replace")}'
            for h in rawHeaderList
            if request.hasRawHeader(h)
        )

    def _start_logger_process(self):
        """
        The subprocess work only on windows, if the plugin is installed with osgeo4w it search for
        the python binary int the same folder has the qgis binary.
        """
        qgisPath = sys.executable
        pythonPath = os.path.join(os.path.split(qgisPath)[0], "python3.exe")
        worker_cmd = [
            pythonPath,
            "-u",
            os.path.join(os.path.dirname(__file__), "network_logger_worker.py"),
            self.filePath,
        ]
        try:
            self._logger_process = subprocess.Popen(
                worker_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            self._logger_stream = self._logger_process.stdin
            self._teardown_fallback_handler()
        except Exception as exc:
            self._logger_process = None
            self._logger_stream = None
            QgsMessageLog.logMessage(
                f"Unable to start network logger worker: {exc}",
                "QGIS Network Logger...",
                Qgis.MessageLevel.Warning,
            )
            self._setup_fallback_handler()

    def _send_to_worker(self, payload):
        """
        Try to send the message to the worker, if it fail try to open a new worker.
        """
        if not self._logger_stream:
            return False
        try:
            self._logger_stream.write(json.dumps(payload) + "\n")
            self._logger_stream.flush()
            return True
        except Exception as exc:
            QgsMessageLog.logMessage(
                f"Network logger worker stopped: {exc}",
                "QGIS Network Logger...",
                Qgis.MessageLevel.Warning,
            )
            self._shutdown_logger_process()
            self._start_logger_process()
            return False

    def _shutdown_logger_process(self):
        """
        Send a stop message to the worker and clean the pointer to the worked and the stream.
        """
        if not self._logger_process:
            return
        try:
            if self._logger_stream:
                try:
                    self._logger_stream.write("__STOP__\n")
                    self._logger_stream.flush()
                except Exception:
                    pass
                self._logger_stream.close()
            self._logger_process.wait(timeout=2)
        except Exception:
            self._logger_process.kill()
        finally:
            self._logger_process = None
            self._logger_stream = None

    def _setup_fallback_handler(self):
        """
        If the python executable is not found it will use this function to write the logs.
        """
        if self._fallback_handler:
            return
        handler = RotatingFileHandler(
            self.filePath, maxBytes=1 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(asctime)s \t %(message)s", "%Y-%m-%d %H:%M:%S"))
        self.logger.addHandler(handler)
        self._fallback_handler = handler

    def _fallback_log(self, payload):
        """
        This function is used as a fallback when the worker is not there, it will run if you are not
        using QGIS installed with osgeo4w in windows.

        It first check if the fallback logger exist, if not it will start the logger and then fire a
        message to the user saying that is using the fallback logger.
        """
        first_use = self._fallback_handler is None
        self._setup_fallback_handler()
        if first_use:
            self.logger.warning("Network logger worker unavailable; using fallback logging.")
        self.logger.info(
            "\t".join(
                [
                    payload.get("event", ""),
                    str(payload.get("request_id", "")),
                    payload.get("operation", ""),
                    payload.get("url", ""),
                    str(payload.get("status", "")),
                    payload.get("details", ""),
                    payload.get("headers", ""),
                ]
            )
        )

    def _teardown_fallback_handler(self):
        """
        This function close the fallback handler if not needed.
        """
        if not self._fallback_handler:
            return
        self.logger.removeHandler(self._fallback_handler)
        self._fallback_handler.close()
        self._fallback_handler = None
