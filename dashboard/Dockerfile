FROM node:20-slim
WORKDIR /app
COPY dashboard/package.json .
RUN npm install
COPY dashboard .
RUN npm run build
CMD ["npm", "start"]
