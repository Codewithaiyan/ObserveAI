# 1. Build Phase
FROM node:20-alpine AS builder
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm install

COPY . .
RUN npm run build

# 2. Run Phase
FROM node:20-alpine
WORKDIR /app

COPY --from=builder /app ./
EXPOSE 3000

ENV HOSTNAME=0.0.0.0
CMD ["npm", "start"]
