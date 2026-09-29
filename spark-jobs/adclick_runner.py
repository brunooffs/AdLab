"""
adclick_runner.py — run adclick_streaming.main() with a way to stop it cleanly.

The plain job blocks until Ctrl+C. This wrapper adds two optional stop conditions:

  STOP_FILE     stop when this file appears      (default /tmp/adlab-spark-stop)
  RUN_SECONDS   stop after N seconds             (default 0 = no limit)

Used by bin/e2e.sh, and by anything else that needs to end the job without killing
the whole Spark application. Submit it exactly like the normal job:

  SPARK_APP=adclick_runner.py ./spark.sh
"""
import os
import threading
import time

from pyspark.sql import SparkSession

import adclick_streaming

STOP_FILE   = os.getenv("STOP_FILE", "/tmp/adlab-spark-stop")
RUN_SECONDS = int(os.getenv("RUN_SECONDS", "0") or 0)


def _watch() -> None:
    started = time.time()
    while True:
        time.sleep(2)
        if os.path.exists(STOP_FILE):
            reason = f"stop file {STOP_FILE} found"
            break
        if RUN_SECONDS > 0 and time.time() - started >= RUN_SECONDS:
            reason = f"RUN_SECONDS={RUN_SECONDS} reached"
            break
    print(f"Stopping streaming queries: {reason}", flush=True)
    # main() builds the session; until then _instantiatedSession is None. Keep
    # stopping until main() returns (the thread is a daemon and dies with it).
    while True:
        spark = SparkSession._instantiatedSession
        if spark is not None:
            for query in spark.streams.active:
                query.stop()
        time.sleep(1)


if __name__ == "__main__":
    if os.path.exists(STOP_FILE):          # a stale file must not stop a fresh run
        os.remove(STOP_FILE)
    threading.Thread(target=_watch, daemon=True).start()
    adclick_streaming.main()
    print("Streaming queries stopped.", flush=True)
