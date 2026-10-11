# ==============================================================================
# S&P 100 NLP Risk Engine — Frontend Dockerfile
# Serves pre-built Vite React production bundle via ultra-light Nginx Alpine (~25MB)
# ==============================================================================

FROM nginx:1.27-alpine

LABEL maintainer="IIT Pune — Code to Connect 2026"
LABEL description="S&P 100 NLP Risk Engine Frontend Dashboard"

# Copy Nginx configuration with reverse proxy & SSE streaming
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy production static files (built with npm run build)
COPY dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=3s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://127.0.0.1/healthz || exit 1

CMD ["nginx", "-g", "daemon off;"]
