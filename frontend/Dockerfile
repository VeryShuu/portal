FROM node:22-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts

COPY . .
RUN npm run build

FROM nginx:1.27-alpine AS production

COPY --from=builder /app/dist /usr/share/nginx/html

COPY nginx.spa.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
