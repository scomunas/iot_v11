# ==============================================================================
# IoT Automation Frontend Dockerfile (Multi-Stage Build)
# ==============================================================================

# Stage 1: Build Angular application
FROM node:24-alpine AS build

WORKDIR /app

# Install dependencies
COPY package*.json ./
RUN npm ci

# Copy application source and build production bundle
COPY . .
RUN npm run build

# Stage 2: Serve using lightweight Nginx
FROM nginx:alpine

# Remove default static files
RUN rm -rf /usr/share/nginx/html/*

# Copy production bundle from build stage
COPY --from=build /app/dist/iot/browser /usr/share/nginx/html

# Copy custom Nginx configuration supporting Angular SPA routing
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy entrypoint script to dynamically inject environment variables (like API_KEY) into config.js
COPY docker-entrypoint.sh /docker-entrypoint.d/40-generate-config.sh
RUN chmod +x /docker-entrypoint.d/40-generate-config.sh

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD wget --quiet --tries=1 --spider http://localhost:80/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
