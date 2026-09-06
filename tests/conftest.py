import os
from tempfile import TemporaryDirectory

_test_data_directory = TemporaryDirectory(prefix="spider-ai-tests-")

os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["SPIDER_AI_DB_PATH"] = str(f"{_test_data_directory.name}/spider-ai-tests.db")
