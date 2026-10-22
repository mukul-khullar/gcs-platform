FROM debian:bookworm-slim AS builder

ARG COPTER_TAG=Copter-4.7.2

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    ccache \
    g++ \
    gcc \
    git \
    gawk \
    libffi-dev \
    libxml2-dev \
    libxslt1-dev \
    make \
    pkg-config \
    python3 \
    python3-dev \
    python3-pip \
    python3-setuptools \
    python3-wheel \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --break-system-packages --no-cache-dir \
    pymavlink==2.4.50 \
    MAVProxy==1.8.75 \
    empy==3.3.4 \
    pexpect==4.9.0

RUN git clone --branch "${COPTER_TAG}" --depth 1 \
    https://github.com/ArduPilot/ardupilot.git /ardupilot \
    && git -C /ardupilot submodule update --init --recursive --depth 1

WORKDIR /ardupilot
RUN ./waf configure --board sitl \
    && ./waf copter -j2

FROM debian:bookworm-slim AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    HOME=/home/sitl \
    PATH="/usr/local/bin:/usr/bin:/bin"

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    libatomic1 \
    libffi8 \
    libgcc-s1 \
    libstdc++6 \
    libxml2 \
    libxslt1.1 \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin sitl

RUN python3 -m pip install --break-system-packages --no-cache-dir \
    pymavlink==2.4.50 \
    MAVProxy==1.8.75 \
    empy==3.3.4 \
    pexpect==4.9.0 \
    PyYAML==6.0.2

COPY --from=builder /ardupilot /ardupilot
COPY tools/check_hb.py /sim/tools/check_hb.py
COPY tools/record_fixture.py /sim/tools/record_fixture.py
COPY corpus/generate.py /sim/corpus/generate.py
COPY corpus/flight.py /sim/corpus/flight.py
COPY corpus/matrix.yaml /sim/corpus/matrix.yaml
COPY simctl/faults.py /sim/simctl/faults.py
RUN chmod 0555 /sim/tools/check_hb.py /sim/tools/record_fixture.py /sim/corpus/generate.py \
    && chown -R sitl:sitl /ardupilot /home/sitl /sim

WORKDIR /ardupilot
USER 10001:10001

HEALTHCHECK --interval=2s --timeout=3s --start-period=10s --retries=20 \
    CMD ["python3", "/sim/tools/check_hb.py", "--in-container", "--connect", "udpin:127.0.0.1:14550", "--timeout", "2"]
