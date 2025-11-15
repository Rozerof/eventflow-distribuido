# Usar la imagen oficial de NGINX
FROM nginx:alpine

# Eliminar la configuración por defecto de NGINX
RUN rm /etc/nginx/conf.d/default.conf

# Copiar nuestra configuración personalizada y la interfaz de usuario al contenedor
COPY nginx.conf /etc/nginx/nginx.conf
COPY index.html /usr/share/nginx/html/index.html