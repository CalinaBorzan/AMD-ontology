FROM nvcr.io/nvidia/pytorch:23.10-py3

ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
# NOTE: torch is NOT listed here — it comes from the base image
RUN pip install \
    langchain_community==0.3.14 \
    langchain_core==0.3.29 \
    langchain_ollama==0.2.2 \
    langchain_openai==0.3.0 \
    langchain-huggingface==0.1.2 \
    pandas==2.2.3 \
    python-dotenv==1.0.1 \
    PyYAML==6.0.2 \
    transformers==4.50.0 \
    evaluate==0.4.3 \
    accelerate \
    rdflib==7.1.4 \
    faiss-cpu==1.10.0

# Install Ollama
RUN curl -fsSL https://ollama.com/install.sh | sh

# Set Ollama models directory to QNAP (mounted at runtime)
ENV OLLAMA_MODELS=/mnt/QNAP/annbor/ollama_models

WORKDIR /workspace

CMD ["/bin/bash"]