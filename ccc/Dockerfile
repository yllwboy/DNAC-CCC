# Configuration Compliance Check
#
# AUTHOR(s): Héctor Cavalcanti Saavedra <hcavalca@cisco.com>
# CONTRIBUTOR(s): Sarah Louise Justin <sajustin@cisco.com>

FROM python:3.9-alpine

# Image Metadata
LABEL com.cisco.author="Héctor Cavalcanti Saavedra <hcavalca@cisco.com>"

WORKDIR /ccc

RUN apk add --update gcc libc-dev gmp python3-dev
COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt

COPY . .

RUN export FLASK_APP=flaskr && flask init-db

CMD ["flask", "run", "--host=0.0.0.0"]