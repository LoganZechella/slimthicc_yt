#!/bin/bash
set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Your Docker Hub username (change if needed)
DOCKER_USERNAME="loganzechella"

# Image name and tag
IMAGE_NAME="slimthicc_yt"
TAG_NAME="latest"

echo -e "${BLUE}=== Building Docker image with CORS fixes ===${NC}"
echo -e "${YELLOW}This will build and push a new version of your backend with CORS support${NC}"

# Build the Docker image
echo -e "${BLUE}Building Docker image...${NC}"
docker build -t $DOCKER_USERNAME/$IMAGE_NAME:$TAG_NAME .

# Push the image to Docker Hub
echo -e "${BLUE}Pushing to Docker Hub...${NC}"
docker push $DOCKER_USERNAME/$IMAGE_NAME:$TAG_NAME

echo -e "${GREEN}=== Deployment complete! ===${NC}"
echo -e "${YELLOW}Next steps:${NC}"
echo -e "1. Go to your Render dashboard: ${BLUE}https://dashboard.render.com${NC}"
echo -e "2. Find your service: ${BLUE}slimthicc_yt-api-latest${NC}"
echo -e "3. Click 'Manual Deploy' and select 'Deploy latest commit'"
echo -e "4. Wait for the deployment to complete"
echo -e "${GREEN}Your backend should now properly handle CORS requests from your Netlify frontend!${NC}" 