import base64
import io
import logging
from typing import Any, Dict, List, Optional, Type

import requests
from langchain.tools import BaseTool
from langgraph.prebuilt import InjectedState
from pydantic import BaseModel, Field
from requests_toolbelt.multipart import decoder
from typing_extensions import Annotated

logger = logging.getLogger(__name__)


class GenezioPythonInterpreterInput(BaseModel):
    code: str = Field(description="code to be executed")
    dependencies: List[str] = Field(
        description="strings representing the dependencies needed to run the code"
    )
    state: Optional[Annotated[dict, InjectedState]]


class GenezioPythonInterpreter(BaseTool):
    name: str = "run_python_code_tool"
    description: str = """
    Run general purpose python code. This can be used to access Internet or do
    any computation that you need. The code will be executed in a remote
    environment. The code can also write files to the "/tmp/output/" folder
    and they will be available in the output. The output will be composed of
    the stdout, stderr and the files written by the code. The code should be
    written in a way that it can be executed in a single file.
    """
    args_schema: Type[BaseModel] = GenezioPythonInterpreterInput
    url: str = ""

    def __init__(
        self,
        url: str,
        envVars: List[str] = [],
        customInstruction: str = "",
        librariesAlreadyInstalled: List[str] = [],
        **kwargs: Any,
    ):
        """
        Constructor for RunPythonCodeTool.

        Args:
            url (str): The URL of the remote execution environment.
                You should first deploy this
                project https://github.com/vladiulianbogdan/genezio-python-executor
                The deployment will return the URL where the execution
                environment is available.
            envVars (List[str]): A list of environment variables that are already
                set on the execution environment and can be used in the code.
            customInstruction (str): A custom instruction that will be added to
                the description of the tool.
            librariesAlreadyInstalled (List[str]): A list of libraries that are
                already installed on the execution environment and you don't have to
                include them in the 'dependencies' array.
            **kwargs: Additional keyword arguments to pass to the parent class.
        """
        super().__init__(**kwargs)  # Call the parent class constructor
        self.description = self.description
        self.url = url

        if envVars:
            self.description += (
                "The following env vars were already set on the execution environment "
                "and they can be used: " + ", ".join(envVars) + "."
            )
        if librariesAlreadyInstalled:
            self.description += (
                " The following libraries were already installed on the execution "
                "environment  and you don't have to include them in the "
                "'dependencies' array:" + ", ".join(librariesAlreadyInstalled) + "."
            )
        if customInstruction:
            self.description += customInstruction

    def _run(
        self,
        code: str,
        dependencies: List[str],
        state: Optional[Annotated[dict, InjectedState]] = None,
        run_manager: Optional[object] = None,
    ) -> Any:
        """
        Runs the provided Python code in the remote execution environment.

        Args:
            code (str): The Python code to execute
            dependencies (List[str]): List of required dependencies
            state Annotated[dict, InjectedState]: The state object
            run_manager (Optional[object]): LangChain callback manager

        Returns:
            str: The execution result or an error message.
        """
        try:
            # Create an in-memory file buffer for the script
            main_script = io.BytesIO(code.encode("utf-8"))

            # Prepare multipart request with all files under the same key
            files = [("files", ("main.py", main_script, "text/x-python"))]

            # Add auxiliary files if provided
            if state:
                for message in state.get("messages", []):
                    for aux_file in message.additional_kwargs.get("files", []):
                        decoded_content = base64.b64decode(aux_file["content"])
                        file_obj = io.BytesIO(decoded_content)
                        file_obj.seek(0)
                        files.append(
                            (
                                "files",
                                (
                                    aux_file["filename"],
                                    file_obj,
                                    aux_file.get(
                                        "content_type", "application/octet-stream"
                                    ),
                                ),
                            )
                        )
            params = {"dependencies": ",".join(dependencies)}

            logger.debug(f"Sending request to {self.url} with deps: {dependencies}")
            response = requests.post(self.url, files=files, params=params)

            logger.debug(f"Response received with status {response.status_code}")

            if response.status_code > 400:
                return {
                    "error": f"Server responded {response.status_code}: {response.text}"
                }
            # Parse multipart response
            multipart_data = decoder.MultipartDecoder(
                response.content, response.headers["Content-Type"]
            )
            output: Dict[str, Any] = {"stdout": "", "stderr": "", "files": {}}

            for part in multipart_data.parts:
                content_disposition = part.headers.get(
                    b"Content-Disposition", b""
                ).decode()
                if 'name="stdout"' in content_disposition:
                    output["stdout"] = part.text
                elif 'name="stderr"' in content_disposition:
                    output["stderr"] = part.text
                elif 'filename="' in content_disposition:
                    filename = content_disposition.split('filename="')[1].split('"')[0]
                    d = base64.b64encode(part.content)
                    output["files"][filename] = d.decode("ascii")

            # Log errors if present
            if output["stderr"]:
                logger.error(f"Execution stderr: {output['stderr']}")

            return output
        except requests.RequestException as e:
            logger.error(f"Request error: {e}")
            return {"error": "Failed to execute code due to a request issue."}

        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return {"error": str(e)}
