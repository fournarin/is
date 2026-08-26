"""The image, the compose file and the code have to name one model and one path.

Three files have to agree for a document to be indexed on a machine with no
internet, and nothing else checks that they do:

  * `Dockerfile` downloads the weights at build time into a directory,
  * `docker-compose.yml` must not point the workers somewhere else,
  * `pdm.retrieval.embedding` reads that directory and asks for that model.

The failure this prevents is quiet in the worst way. fastembed downloads a model
it cannot find, so a mismatch does not raise on a developer's machine: it
downloads 0.22 GB, works, and passes CI. On the plant's machine - no route out,
ADR-029 - the same code fails at the first uploaded document with a TLS error
that says nothing about a model (ADR-079).
"""

from __future__ import annotations

import re
from pathlib import Path

from pdm.retrieval.embedding import DEFAULT_MODEL, MODEL_CACHE_VARIABLE

DOCKERFILE = Path("Dockerfile").read_text(encoding="utf-8")
COMPOSE = Path("docker-compose.yml").read_text(encoding="utf-8")


class TestTheImageCarriesTheWeights:
    def test_the_build_downloads_a_model_into_the_cache_it_declares(self) -> None:
        declared = re.search(rf"ENV {MODEL_CACHE_VARIABLE}=(\S+)", DOCKERFILE)
        assert declared is not None, f"the image sets no {MODEL_CACHE_VARIABLE}"
        path = declared.group(1)
        assert f"mkdir -p {path}" in DOCKERFILE
        assert "OnnxEmbedder()" in DOCKERFILE, (
            "the build must construct the embedder, which is what makes fastembed "
            "fetch the weights - a bare mkdir ships an empty directory"
        )

    def test_the_baked_model_is_the_one_the_code_asks_for(self) -> None:
        """Named through the module rather than repeated as a string, so this can
        only be broken deliberately."""
        assert "DEFAULT_MODEL" in DOCKERFILE
        assert DEFAULT_MODEL not in DOCKERFILE, (
            "the model name is spelled out in the Dockerfile; import it from "
            "pdm.retrieval.embedding instead, or the two drift apart in silence"
        )

    def test_the_weights_belong_to_the_user_that_runs_the_worker(self) -> None:
        """Nothing runs as root here, and a cache the runtime user cannot read is
        a model that is downloaded again on every start - if there is a network,
        and a failure if there is not."""
        declared = re.search(rf"ENV {MODEL_CACHE_VARIABLE}=(\S+)", DOCKERFILE)
        assert declared is not None
        chown = re.search(r"chown -R pdm:pdm ([^\n]+)", DOCKERFILE)
        assert chown is not None
        assert declared.group(1) in chown.group(1)


class TestNothingPointsTheWorkersSomewhereElse:
    def test_compose_does_not_override_the_cache_path(self) -> None:
        """It may set it - to the same value, or to a mounted volume - but a
        different path is a worker looking in an empty directory."""
        declared = re.search(rf"ENV {MODEL_CACHE_VARIABLE}=(\S+)", DOCKERFILE)
        assert declared is not None
        for line in COMPOSE.splitlines():
            if MODEL_CACHE_VARIABLE in line:
                assert declared.group(1) in line, (
                    f"{line.strip()!r} points somewhere the image did not bake"
                )
