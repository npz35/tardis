#!/bin/bash

docker-compose exec app curl -X POST http://host.docker.internal:11435/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer none" \
  -d '{
    "model": "default-model",
    "messages": [
      {
        "role": "system",
        "content": "You are a helpful assistant."
      },
      {
        "role": "user",
        "content": "who are you?"
      }
    ],
    "stream": "False"
  }'
