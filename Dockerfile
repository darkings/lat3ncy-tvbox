FROM python:3.11-slim

# Install Node.js, ffmpeg, cron, and uv
RUN sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && apt-get install -y \
    nodejs \
    npm \
    ffmpeg \
    cron \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="/usr/local/bin" sh

# Create a non-root user
RUN useradd -m -s /bin/bash ponyo

WORKDIR /app

# Copy project files
COPY pyproject.toml README.md uv.lock ./
COPY src ./src
COPY config ./config
COPY drpy2 ./drpy2

# Install project and dependencies
RUN uv pip install --system -i https://pypi.tuna.tsinghua.edu.cn/simple -e .

# Setup permissions
RUN chown -R ponyo:ponyo /app

USER ponyo
ENV PONYO_ROOT=/app

# By default run the scheduler quick phase
CMD ["python", "-m", "ponyo_source_manager.scheduler", "--phase", "quick"]
