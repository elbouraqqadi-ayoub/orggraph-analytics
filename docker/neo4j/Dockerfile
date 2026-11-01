FROM neo4j:5.26-community@sha256:414adfe41c6ff32abb752be37f265c77607c166cab298f65a917fc4f05776218
USER root
COPY --chown=neo4j:neo4j .runtime/neo4j/neo4j-graph-data-science-2.13.14.jar /plugins/neo4j-graph-data-science.jar
RUN chown neo4j:neo4j /plugins
