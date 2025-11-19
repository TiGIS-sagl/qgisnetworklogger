Experimental QGIS plugin to log HTTP requests to a file.
This is a fork of the original [plugin](https://github.com/nyalldawson/qgisnetworklogger) by Richard Duivenvoorde.

This plugin is useful for identifying which HTTP call leads to a QGIS crash. It provides less information than the built‑in developer network logger, but since the logs are written to a file, they remain available after QGIS crashes.

Test only in QGIS 3.40 it work also with QT6.

Current limitations:
- Header information is not recorded. Only the URL of each operation and the body of PUT and POST requests are logged.

To use:
- Install plugin.
- Select a file where the log will be stored.