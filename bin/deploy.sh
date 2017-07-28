#!/usr/bin/env bash
set -eo pipefail

# default variables
: "${CIRCLE_TAG:=latest}"

# Usage: retry MAX CMD...
# Retry CMD up to MAX times. If it fails MAX times, returns failure.
# Example: retry 3 docker push "mozilla/telemetry-analysis-service:$TAG"
function retry() {
    max=$1
    shift
    count=1
    until "$@"; do
        count=$((count + 1))
        if [[ $count -gt $max ]]; then
            return 1
        fi
        echo "$count / $max"
    done
    return 0
}

echo "Logging into Docker hub"
retry 3 docker login -e="$DOCKER_EMAIL" -u="$DOCKER_USER" -p="$DOCKER_PASS"

echo "Tagging app:build with $CIRCLE_TAG"
docker tag app:build "$DOCKERHUB_REPO:$CIRCLE_TAG" ||
  (echo "Couldn't tag app:build as $DOCKERHUB_REPO:$CIRCLE_TAG" && false)

echo "Pushing tag $CIRCLE_TAG to $DOCKERHUB_REPO"
retry 3 docker push "$DOCKERHUB_REPO:$CIRCLE_TAG" ||
  (echo "Couldn't push $DOCKERHUB_REPO:$CIRCLE_TAG" && false)

 echo "Pushed $DOCKERHUB_REPO:$TAG"
