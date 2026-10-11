# ==============================================================================
# S&P 100 NLP Risk Engine — Frontend Dockerfile (Multi-stage build)
# Builds Vite React bundle with Node 20 and serves via ultra-light Nginx Alpine
# ==============================================================================

# Stage 1: Build production React bundle
FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies using clean install
COPY package.json package-lock.json ./
RUN npm ci

# Copy frontend source files
COPY . .

# Build production assets (outputs to /app/dist)
RUN npm run build

# Stage 2: Serve with lightweight Nginx
FROM nginx:1.27-alpine

LABEL maintainer="IIT Pune — Code to Connect 2026"
LABEL description="S&P 100 NLP Risk Engine Frontend Dashboard"

# Replace default Nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy compiled static assets from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Expose HTTP port
EXPOSE 80

# Health check
HEALTHCHECK --interval=15s --timeout=3s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost/healthz || exit 1

# Run Nginx in foreground
CMD ["nginx", "-g", "daemon off;"]
