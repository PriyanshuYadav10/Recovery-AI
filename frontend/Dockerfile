# Recovery AI console - Flutter web, built and served behind nginx.
FROM debian:bookworm-slim AS build

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git ca-certificates unzip xz-utils \
    && rm -rf /var/lib/apt/lists/*

# Flutter's artifact downloader extracts SDK tarballs with tar's ownership
# preservation, which only kicks in when running as root - and some build
# sandboxes (e.g. Render's) reject a few of the UIDs baked into those
# tarballs with "Cannot change ownership ... Invalid argument". Building as
# a normal user sidesteps it: non-root tar never attempts the chown.
RUN useradd --create-home --shell /bin/bash flutter
ENV FLUTTER_HOME=/home/flutter/flutter
RUN git clone --depth 1 --branch stable https://github.com/flutter/flutter.git $FLUTTER_HOME \
    && chown -R flutter:flutter $FLUTTER_HOME

USER flutter
ENV PATH="$FLUTTER_HOME/bin:$PATH"
RUN flutter precache --web && flutter config --enable-web

WORKDIR /home/flutter/app
COPY --chown=flutter:flutter pubspec.yaml pubspec.lock ./
RUN flutter pub get
COPY --chown=flutter:flutter . .

# Backend URL to bake into the compiled JS. Override with:
#   docker build --build-arg API_BASE_URL=https://your-backend.example.com .
ARG API_BASE_URL=http://127.0.0.1:8000
RUN flutter build web --release --dart-define=API_BASE_URL=${API_BASE_URL}

FROM nginx:1.27-alpine
COPY --from=build /home/flutter/app/build/web /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
