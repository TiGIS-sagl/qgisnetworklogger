QGIS plugin for logging HTTP requests to a TSV log file
=======================================================

This plugin is a fork of the [**QgisNetworkLogger**](https://github.com/nyalldawson/qgisnetworklogger)  
plugin originally created by Richard Duivenvoorde. Unlike the original plugin,  
this fork focuses on logging requests to a file rather than providing a graphical  
interface to inspect them.

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

The log is written as a tab-separated values (TSV) file with log rotation. When the  
current file reaches 1 MB, it is rotated and up to 3 backup files are kept.

Architecture and multiprocessing
--------------------------------

To avoid blocking QGIS while writing to disk, the plugin uses a separate **worker process**  
for logging on supported setups:

- The main QGIS process serializes each network event as JSON and sends it via stdin  
  to a worker Python process (`network_logger_worker.py`).
- The worker runs in a plain Python environment (no QGIS dependencies) and appends the  
event to the TSV log using a `RotatingFileHandler`.
- If the worker process cannot be started or becomes unavailable, the plugin falls back  
  to logging directly from the QGIS process using the same rotating log format.

This multiprocessing approach keeps logging fast and reduces the risk that slow disk I/O  
impacts QGIS responsiveness.

Usage
-----

### Selecting the log file

On first use, the plugin asks you to select a log file path:

- A file dialog (`Select log file`) is shown when the plugin is initialized.
- The chosen path is stored in the global expression variable `network_log_file`.
- On subsequent QGIS sessions, the plugin reuses this stored path and no dialog is shown  
  unless the variable is removed or QGIS is reset.

You can change the log file by clearing or editing the `network_log_file` global variable:

1. Open `Settings` → `Options…` → `Variables` (Global variables).  
2. Locate `network_log_file` and change or delete its value.  
3. Restart QGIS, then re-enable the plugin to select a new log file.

### Enabling or disabling message log output

The plugin can optionally mirror network events to the QGIS message log:

- Use the menu entry `QGIS Network Logger` (under the `Plugins` menu).
- A dialog shows the current log file path and asks whether to enable log messages.
- Clicking **Yes** enables messages in the QGIS log (`Log Messages` panel).  
- Clicking **No** disables these messages; logging to the TSV file continues either way.

Only the in-QGIS messages are toggled by this dialog. The TSV file logging is always active  
as long as the plugin is enabled.

Compatibility
-------------

The multiprocessing worker is currently designed and tested for **Windows** installations  
using **OSGeo4W**:

- The plugin looks for `python3.exe` in the same directory as the `qgis.exe` executable  
  (the standard OSGeo4W layout) and launches the worker from there.
- On this configuration, logging runs in a dedicated Python process and QGIS remains  
  responsive even under heavy network traffic.

On other operating systems or non-OSGeo4W layouts, the worker process may not start  
correctly. In that case, the plugin automatically **disables multiprocessing** and logs  
 directly from the main QGIS process. Logging will still work, but it may:

- slightly slow down QGIS when a very large number of requests are logged
- be more susceptible to losing the last few log lines if QGIS crashes abruptly

The plugin has been tested only on **Windows** with **QGIS 3.40** builds for both **Qt5** and **Qt6**.

Limitations
-----------

- No queue is currently implemented between QGIS and the worker, so bursts of logs rely on the OS pipe buffering.
- There is no GUI to configure the log rotation size or the number of backups; these values are hard-coded (1 MB, 3 backups).
- There is no GUI to change the log file path or adjust log verbosity/levels after the initial variable is set, and no log levels exist at all: the plugin is designed for diagnosing intermittently crashing clients that can also take down servers even when HTTP calls apparently succeed, so capturing every request (not just errors) is intentional.
