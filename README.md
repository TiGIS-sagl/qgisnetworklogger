QGIS plugin for logging HTTP requests to a TSV log file
=======================================================

This plugin is a fork of the [**QgisNetworkLogger**](https://github.com/nyalldawson/qgisnetworklogger) plugin originally created by
Richard Duivenvoorde. Unlike the original plugin, this fork focuses on logging
requests to a file rather than providing a graphical interface to inspect them.

Compared to the QGIS developer tools, this plugin writes every request sent from
the client to the server to a TSV file, so that HTTP logs remain available even
after an unexpected QGIS crash. The following information is logged:

- request ID  
- HTTP method  
- URL  
- headers  
- payload data for `POST` and `PUT` requests  
- HTTP status code
- error description
- response length

Compatibility
-------------

The plugin has been tested only with **QGIS 3.40** and also supports **Qt6**.