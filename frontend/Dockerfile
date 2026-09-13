FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci --no-audit --no-fund
COPY . .
# 构建时注入高德 Key（由构建变量传入，避免写入源码）
ARG VITE_AMAP_KEY=
ENV VITE_AMAP_KEY=$VITE_AMAP_KEY
# 兼容运行时注入：也可通过 index.html meta 覆盖
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]