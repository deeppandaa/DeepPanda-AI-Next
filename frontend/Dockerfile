FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html /usr/share/nginx/html/index.html
COPY app.js /usr/share/nginx/html/app.js
COPY legacy-history.js /usr/share/nginx/html/legacy-history.js
COPY legacy-memory.js /usr/share/nginx/html/legacy-memory.js
COPY tools.js /usr/share/nginx/html/tools.js
COPY cloud.js /usr/share/nginx/html/cloud.js
COPY styles.css /usr/share/nginx/html/styles.css
COPY pe-lab.html /usr/share/nginx/html/pe-lab.html
COPY pe-lab.js /usr/share/nginx/html/pe-lab.js
COPY pe-lab.css /usr/share/nginx/html/pe-lab.css