FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
# npm ci 而非 npm install：package-lock.json 已入库（59.1KB），
# npm ci 严格按锁文件安装，依赖版本可复现，且node_modules 会被整体清空重建
# —— 后者很关键：下面的 `COPY . .` 若带进宿主机的 node_modules，
# 跨平台原生二进制（esbuild/rollup 的 .node）会与刚装好的那份不一致而构建失败。
# 前提是 .dockerignore 排除了 node_modules/，两者必须成对存在。
RUN npm ci
COPY . .
RUN npm run build
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80

