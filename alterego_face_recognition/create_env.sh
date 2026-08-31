#!/usr/bin/env bash
set -e

ENV_NAME="face_tracking_test"
REQUIREMENTS_FILE="requirements.txt"

if [[ ! -f "$REQUIREMENTS_FILE" ]]; then
  echo "Errore: $REQUIREMENTS_FILE non trovato."
  exit 1
fi

source "$(conda info --base)/etc/profile.d/conda.sh"

if ! conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
  echo "Creazione dell'ambiente Conda: $ENV_NAME"
  conda create --name "$ENV_NAME" --yes python=3.10
else
  echo "L'ambiente $ENV_NAME esiste già."
fi

echo "Attivazione dell'ambiente: $ENV_NAME"
conda activate "$ENV_NAME"

if ! python -m pip --version > /dev/null 2>&1; then
  echo "Errore: pip non è stato trovato nell'ambiente Conda '$ENV_NAME'."
  exit 1
fi

echo "Aggiornamento di pip"
python -m pip install --upgrade pip

echo "Installazione dei pacchetti da $REQUIREMENTS_FILE"
python -m pip install -r "$REQUIREMENTS_FILE"

echo "Ambiente $ENV_NAME configurato con successo."