FROM node:20-alpine
WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev --no-audit --no-fund
COPY . .
# Keys are generated at build time if not mounted; compose/k8s mount real ones.
RUN node src/genkeys.js || true
EXPOSE 8080
HEALTHCHECK --interval=5s --timeout=3s --retries=5 CMD wget -qO- http://localhost:8080/health || exit 1
CMD ["node", "server.js"]
