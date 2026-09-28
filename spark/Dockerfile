# Spark with the Kafka source and Elasticsearch sink connectors baked in.
# Replaces the unversioned *.jar files that used to be committed under spark-jobs/.
#
# Keep these versions consistent when you upgrade:
#   spark-sql-kafka, spark-token-provider  -> the same version as SPARK_VERSION (Scala 2.12 build)
#   kafka-clients, commons-pool2           -> the versions in Spark's own pom.xml
#                                             (Spark 3.5.3, 3.5.8 and 3.5.9 all use 3.4.1 and 2.11.1)
#   elasticsearch-spark                    -> the Elasticsearch version you run
ARG SPARK_VERSION=3.5.9
FROM apache/spark:${SPARK_VERSION}

ARG SPARK_VERSION
ARG SCALA_BINARY=2.12
ARG KAFKA_CLIENTS_VERSION=3.4.1
ARG COMMONS_POOL2_VERSION=2.11.1
ARG ES_SPARK_VERSION=8.13.4
ARG MAVEN=https://repo1.maven.org/maven2

ADD --chown=spark:spark --chmod=644 ${MAVEN}/org/apache/spark/spark-sql-kafka-0-10_${SCALA_BINARY}/${SPARK_VERSION}/spark-sql-kafka-0-10_${SCALA_BINARY}-${SPARK_VERSION}.jar /opt/spark/jars/
ADD --chown=spark:spark --chmod=644 ${MAVEN}/org/apache/spark/spark-token-provider-kafka-0-10_${SCALA_BINARY}/${SPARK_VERSION}/spark-token-provider-kafka-0-10_${SCALA_BINARY}-${SPARK_VERSION}.jar /opt/spark/jars/
ADD --chown=spark:spark --chmod=644 ${MAVEN}/org/apache/kafka/kafka-clients/${KAFKA_CLIENTS_VERSION}/kafka-clients-${KAFKA_CLIENTS_VERSION}.jar /opt/spark/jars/
ADD --chown=spark:spark --chmod=644 ${MAVEN}/org/apache/commons/commons-pool2/${COMMONS_POOL2_VERSION}/commons-pool2-${COMMONS_POOL2_VERSION}.jar /opt/spark/jars/
ADD --chown=spark:spark --chmod=644 ${MAVEN}/org/elasticsearch/elasticsearch-spark-30_${SCALA_BINARY}/${ES_SPARK_VERSION}/elasticsearch-spark-30_${SCALA_BINARY}-${ES_SPARK_VERSION}.jar /opt/spark/jars/
