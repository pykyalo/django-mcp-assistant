"""
MCP Server definitions with robust PDF extraction
"""

from typing import List, Dict, Any, Tuple
import os
from pathlib import Path
import pypdf
import pdfplumber
import subprocess
import tempfile


class MCPServer:
    """Base class for MCP servers"""

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description

    def get_tools(self) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def get_resources(self) -> List[Dict[str, Any]]:
        raise NotImplementedError

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        raise NotImplementedError

    async def read_resource(self, uri: str) -> str:
        raise NotImplementedError


class VoIPDocsServer(MCPServer):
    """MCP server for VoIP documentation with robust PDF extraction"""

    def __init__(self, docs_dir: str):
        super().__init__(
            name="voip-docs",
            description="Access to VoIP and SIP protocol documentation",
        )
        self.docs_dir = Path(docs_dir)
        print(f"VoIP Docs Directory: {self.docs_dir}")

    def _validate_pdf(self, pdf_path: Path) -> Tuple[bool, str]:
        """
        Validate PDF file before extraction.
        Returns: (is_valid, message)
        """
        if not pdf_path.exists():
            return False, "File does not exist"

        if pdf_path.stat().st_size == 0:
            return False, "File is empty"

        # Check PDF header
        try:
            with open(pdf_path, "rb") as f:
                header = f.read(8)

                # Valid PDF should start with %PDF
                if not header.startswith(b"%PDF"):
                    # Check if it's a corrupted/special PDF
                    if header.startswith(b"\x00\x00\x00\x00"):
                        return False, "PDF has null bytes at start (possibly corrupted)"
                    return False, f"Invalid PDF header: {header[:20]}"

                return True, "Valid PDF header"
        except Exception as e:
            return False, f"Cannot read file: {str(e)}"

    def _extract_with_pdftotext(
        self, pdf_path: Path, max_pages: int = 30
    ) -> Tuple[str, bool]:
        """
        Extract using pdftotext command-line tool (if available).
        This is often more robust than Python libraries.
        """
        try:
            print(f"  Trying pdftotext (command-line)...")

            # Check if pdftotext is available
            result = subprocess.run(
                ["which", "pdftotext"], capture_output=True, text=True
            )

            if result.returncode != 0:
                print(f"  pdftotext not installed (install via: brew install poppler)")
                return "", False

            # Create temp file for output
            with tempfile.NamedTemporaryFile(
                mode="w+", suffix=".txt", delete=False
            ) as tmp:
                tmp_path = tmp.name

            try:
                # Run pdftotext
                subprocess.run(
                    ["pdftotext", "-l", str(max_pages), str(pdf_path), tmp_path],
                    check=True,
                    capture_output=True,
                    timeout=30,
                )

                # Read extracted text
                with open(tmp_path, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()

                # Clean up
                os.unlink(tmp_path)

                if len(text) > 500:
                    print(f"  pdftotext extracted {len(text)} characters")
                    return text, True
                else:
                    print(f"  pdftotext extracted only {len(text)} characters")
                    return text, False

            except subprocess.TimeoutExpired:
                print(f"  pdftotext timed out")
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                return "", False
            except subprocess.CalledProcessError as e:
                print(
                    f"  pdftotext failed: {e.stderr.decode() if e.stderr else 'Unknown error'}"
                )
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                return "", False

        except Exception as e:
            print(f"  pdftotext error: {str(e)}")
            return "", False

    def _extract_pdf_with_pypdf(
        self, pdf_path: Path, max_pages: int = 30
    ) -> Tuple[str, bool]:
        """Extract text using pypdf library."""
        try:
            print(f"  Trying pypdf extraction...")
            text_content = []

            with open(pdf_path, "rb") as file:
                pdf_reader = pypdf.PdfReader(file)
                total_pages = len(pdf_reader.pages)
                pages_to_extract = min(max_pages, total_pages)

                print(
                    f"  PDF has {total_pages} pages, extracting first {pages_to_extract}"
                )

                for page_num in range(pages_to_extract):
                    try:
                        page = pdf_reader.pages[page_num]
                        page_text = page.extract_text()

                        if page_text and page_text.strip():
                            text_content.append(
                                f"--- Page {page_num + 1} ---\n{page_text}"
                            )
                    except Exception as e:
                        print(f"  Error on page {page_num + 1}: {str(e)}")
                        continue

                result = "\n\n".join(text_content)

                if len(result) > 500:
                    print(
                        f"  pypdf extracted {len(result)} characters from {len(text_content)} pages"
                    )
                    return result, True
                else:
                    print(f"   pypdf extracted only {len(result)} characters")
                    return result, False

        except pypdf.errors.PdfReadError as e:
            print(f"  ❌ pypdf failed (PDF read error): {str(e)}")
            return "", False
        except Exception as e:
            print(f"  ❌ pypdf failed: {str(e)}")
            return "", False

    def _extract_pdf_with_pdfplumber(
        self, pdf_path: Path, max_pages: int = 30
    ) -> Tuple[str, bool]:
        """Extract text using pdfplumber library."""
        try:
            print(f"  Trying pdfplumber extraction...")
            text_content = []

            with pdfplumber.open(pdf_path) as pdf:
                total_pages = len(pdf.pages)
                pages_to_extract = min(max_pages, total_pages)

                print(
                    f"  PDF has {total_pages} pages, extracting first {pages_to_extract}"
                )

                for page_num in range(pages_to_extract):
                    try:
                        page = pdf.pages[page_num]
                        page_text = page.extract_text()

                        if page_text and page_text.strip():
                            text_content.append(
                                f"--- Page {page_num + 1} ---\n{page_text}"
                            )
                    except Exception as e:
                        print(f"  Error on page {page_num + 1}: {str(e)}")
                        continue

                result = "\n\n".join(text_content)

                if len(result) > 500:
                    print(
                        f" pdfplumber extracted {len(result)} characters from {len(text_content)} pages"
                    )
                    return result, True
                else:
                    print(f"  pdfplumber extracted only {len(result)} characters")
                    return result, False

        except Exception as e:
            print(f"  pdfplumber failed: {str(e)}")
            return "", False

    def _try_repair_pdf(self, pdf_path: Path) -> Tuple[Path, bool]:
        """
        Attempt to repair corrupted PDF using ghostscript.
        Returns: (repaired_pdf_path, success)
        """
        try:
            print(f"  Attempting PDF repair with ghostscript...")

            # Check if gs is available
            result = subprocess.run(["which", "gs"], capture_output=True, text=True)

            if result.returncode != 0:
                print(
                    f"  ghostscript not installed (install via: brew install ghostscript)"
                )
                return pdf_path, False

            # Create temp file for repaired PDF
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                repaired_path = Path(tmp.name)

            # Run ghostscript to repair
            subprocess.run(
                [
                    "gs",
                    "-o",
                    str(repaired_path),
                    "-sDEVICE=pdfwrite",
                    "-dPDFSETTINGS=/prepress",
                    str(pdf_path),
                ],
                check=True,
                capture_output=True,
                timeout=60,
            )

            print(f" PDF repaired, saved to temp file")
            return repaired_path, True

        except subprocess.TimeoutExpired:
            print(f"  PDF repair timed out")
            return pdf_path, False
        except subprocess.CalledProcessError as e:
            print(
                f" PDF repair failed: {e.stderr.decode() if e.stderr else 'Unknown error'}"
            )
            return pdf_path, False
        except Exception as e:
            print(f"  PDF repair error: {str(e)}")
            return pdf_path, False

    def _extract_pdf_text(self, pdf_path: Path) -> str:
        """
        Extract text from PDF using multiple methods with fallback.

        Strategy:
        1. Validate PDF file
        2. Try command-line pdftotext (most robust)
        3. Try pypdf
        4. Try pdfplumber
        5. If all fail and PDF seems corrupted, try repair then re-extract
        """

        print(f"\nExtracting PDF: {pdf_path.name}")

        # Step 1: Validate PDF
        is_valid, validation_msg = self._validate_pdf(pdf_path)
        print(f"  Validation: {validation_msg}")

        if not is_valid:
            # Try to repair if corrupted
            repaired_path, repair_success = self._try_repair_pdf(pdf_path)

            if repair_success:
                print(f"  Using repaired PDF for extraction")
                pdf_path = repaired_path
            else:
                return f"Error: {validation_msg}. PDF repair also failed."

        # Step 2: Try pdftotext (command-line tool - most robust)
        pdftotext_text, pdftotext_success = self._extract_with_pdftotext(pdf_path)
        if pdftotext_success:
            print(f"Using pdftotext extraction ({len(pdftotext_text)} chars)")
            return pdftotext_text

        # Step 3: Try pypdf
        pypdf_text, pypdf_success = self._extract_pdf_with_pypdf(pdf_path)
        if pypdf_success:
            print(f"Using pypdf extraction ({len(pypdf_text)} chars)")
            return pypdf_text

        # Step 4: Try pdfplumber
        pdfplumber_text, pdfplumber_success = self._extract_pdf_with_pdfplumber(
            pdf_path
        )
        if pdfplumber_success:
            print(f"Using pdfplumber extraction ({len(pdfplumber_text)} chars)")
            return pdfplumber_text

        # Step 5: All methods failed - return best attempt
        all_results = [
            (pdftotext_text, "pdftotext"),
            (pypdf_text, "pypdf"),
            (pdfplumber_text, "pdfplumber"),
        ]

        # Sort by length and pick longest
        all_results.sort(key=lambda x: len(x[0]), reverse=True)
        best_text, best_method = all_results[0]

        if len(best_text) > 0:
            print(
                f"All methods struggled, using best result from {best_method} ({len(best_text)} chars)"
            )
            return best_text
        else:
            error_msg = f"""Error: Could not extract text from PDF using any method.

                    Tried:
                    - pdftotext (command-line): {"Not installed" if not pdftotext_success else "Failed"}
                    - pypdf library: Failed
                    - pdfplumber library: Failed

                    Suggestions:
                    1. Check if PDF is encrypted/password-protected
                    2. Try opening the PDF in a viewer to verify it's not corrupted
                    3. Install poppler for pdftotext: brew install poppler
                    4. Install ghostscript for PDF repair: brew install ghostscript
                    5. Try re-downloading the PDF if it's corrupted
            """

            print(f"{error_msg}")
            return error_msg

    def get_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "search_voip_docs",
                "description": "Search through VoIP documentation for specific topics. Returns relevant excerpts from SIP RFCs, FreeSWITCH docs, etc. Supports both text files and PDF documents.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query (e.g., 'SIP INVITE method', 'FreeSWITCH dialplan', 'call routing')",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of results to return",
                            "default": 3,
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "get_sip_message_example",
                "description": "Get example SIP messages for different scenarios (INVITE, REGISTER, BYE, etc.)",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "message_type": {
                            "type": "string",
                            "enum": [
                                "INVITE",
                                "REGISTER",
                                "BYE",
                                "CANCEL",
                                "ACK",
                                "OPTIONS",
                            ],
                            "description": "Type of SIP message",
                        }
                    },
                    "required": ["message_type"],
                },
            },
            {
                "name": "list_available_docs",
                "description": "List all available VoIP documentation files in the system",
                "input_schema": {"type": "object", "properties": {}, "required": []},
            },
        ]

    def get_resources(self) -> List[Dict[str, Any]]:
        """List available documentation files (TXT and PDF)"""
        resources = []

        if not self.docs_dir.exists():
            print(f"Documentation directory does not exist: {self.docs_dir}")
            return resources

        for doc_file in self.docs_dir.glob("*.txt"):
            resources.append(
                {
                    "uri": f"file://{doc_file}",
                    "name": doc_file.stem,
                    "description": f"VoIP documentation: {doc_file.stem}",
                    "mimeType": "text/plain",
                }
            )

        for doc_file in self.docs_dir.glob("*.pdf"):
            resources.append(
                {
                    "uri": f"file://{doc_file}",
                    "name": doc_file.stem,
                    "description": f"VoIP PDF: {doc_file.stem}",
                    "mimeType": "application/pdf",
                }
            )

        print(f"Found {len(resources)} documentation files")
        return resources

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Execute tool calls"""

        if tool_name == "search_voip_docs":
            return await self._search_docs(
                arguments["query"], arguments.get("max_results", 3)
            )

        elif tool_name == "get_sip_message_example":
            return self._get_sip_example(arguments["message_type"])

        elif tool_name == "list_available_docs":
            return self._list_docs()

        else:
            return {"error": f"Unknown tool: {tool_name}"}

    async def _search_docs(self, query: str, max_results: int) -> Dict[str, Any]:
        """Search through documentation files (TXT and PDF)"""

        print(f"\nSearching for: '{query}'")

        results = []
        query_lower = query.lower()

        if not self.docs_dir.exists():
            return {
                "results": [],
                "message": f"Documentation directory not found: {self.docs_dir}",
            }

        # Search through text files
        for doc_file in self.docs_dir.glob("*.txt"):
            try:
                content = doc_file.read_text()

                if query_lower in content.lower():
                    lines = content.split("\n")
                    matches = []

                    for i, line in enumerate(lines):
                        if query_lower in line.lower():
                            start = max(0, i - 2)
                            end = min(len(lines), i + 3)
                            context = "\n".join(lines[start:end])
                            matches.append(context)

                            if len(matches) >= max_results:
                                break

                    if matches:
                        results.append(
                            {
                                "file": doc_file.name,
                                "type": "text",
                                "matches": matches[:max_results],
                            }
                        )
                        print(f"  ✓ Found {len(matches)} matches in {doc_file.name}")

            except Exception as e:
                print(f"  ✗ Error reading {doc_file.name}: {e}")
                continue

        # Search through PDF files
        for doc_file in self.docs_dir.glob("*.pdf"):
            try:
                print(f"  Searching PDF: {doc_file.name}")

                # Extract text from PDF
                content = self._extract_pdf_text(doc_file)

                if content.startswith("Error:"):
                    print(f"  ✗ Could not extract text from {doc_file.name}")
                    continue

                if query_lower in content.lower():
                    lines = content.split("\n")
                    matches = []

                    for i, line in enumerate(lines):
                        if query_lower in line.lower():
                            start = max(0, i - 2)
                            end = min(len(lines), i + 3)
                            context = "\n".join(lines[start:end])
                            matches.append(context)

                            if len(matches) >= max_results:
                                break

                    if matches:
                        results.append(
                            {
                                "file": doc_file.name,
                                "type": "pdf",
                                "matches": matches[:max_results],
                            }
                        )
                        print(f" Found {len(matches)} matches in {doc_file.name}")

            except Exception as e:
                print(f"Error searching PDF {doc_file.name}: {e}")
                continue

        print(f"Search complete: {len(results)} files with matches\n")

        return {
            "results": results[:max_results],
            "query": query,
            "total_found": len(results),
        }

    def _list_docs(self) -> Dict[str, Any]:
        """List all available documentation files"""

        if not self.docs_dir.exists():
            return {
                "documents": [],
                "message": f"Documentation directory not found: {self.docs_dir}",
            }

        docs = []

        for doc_file in self.docs_dir.glob("*.txt"):
            docs.append(
                {
                    "name": doc_file.name,
                    "type": "text",
                    "size": f"{doc_file.stat().st_size / 1024:.1f} KB",
                }
            )

        for doc_file in self.docs_dir.glob("*.pdf"):
            # Validate PDF
            is_valid, msg = self._validate_pdf(doc_file)

            docs.append(
                {
                    "name": doc_file.name,
                    "type": "pdf",
                    "size": f"{doc_file.stat().st_size / 1024:.1f} KB",
                    "status": "valid" if is_valid else f"invalid ({msg})",
                }
            )

        return {
            "documents": docs,
            "total_count": len(docs),
            "directory": str(self.docs_dir),
        }

    def _get_sip_example(self, message_type: str) -> str:
        """Return example SIP messages"""

        examples = {
            "INVITE": """INVITE sip:bob@biloxi.com SIP/2.0
            Via: SIP/2.0/UDP pc33.atlanta.com;branch=z9hG4bKnashds8
            Max-Forwards: 70
            To: Bob <sip:bob@biloxi.com>
            From: Alice <sip:alice@atlanta.com>;tag=1928301774
            Call-ID: a84b4c76e66710@pc33.atlanta.com
            CSeq: 314159 INVITE
            Contact: <sip:alice@pc33.atlanta.com>
            Content-Type: application/sdp
            Content-Length: 142

            (SDP content here)""",
            "REGISTER": """REGISTER sip:registrar.biloxi.com SIP/2.0
            Via: SIP/2.0/UDP bobspc.biloxi.com:5060;branch=z9hG4bKnashds7
            Max-Forwards: 70
            To: Bob <sip:bob@biloxi.com>
            From: Bob <sip:bob@biloxi.com>;tag=456248
            Call-ID: 843817637684230@998sdasdh09
            CSeq: 1826 REGISTER
            Contact: <sip:bob@192.0.2.4>
            Expires: 7200
            Content-Length: 0""",
            "BYE": """BYE sip:alice@pc33.atlanta.com SIP/2.0
            Via: SIP/2.0/UDP 192.0.2.4;branch=z9hG4bKnashds10
            Max-Forwards: 70
            From: Bob <sip:bob@biloxi.com>;tag=a6c85cf
            To: Alice <sip:alice@atlanta.com>;tag=1928301774
            Call-ID: a84b4c76e66710
            CSeq: 231 BYE
            Content-Length: 0""",
            "ACK": """ACK sip:bob@192.0.2.4 SIP/2.0
            Via: SIP/2.0/UDP pc33.atlanta.com;branch=z9hG4bKnashds9
            Max-Forwards: 70
            To: Bob <sip:bob@biloxi.com>;tag=a6c85cf
            From: Alice <sip:alice@atlanta.com>;tag=1928301774
            Call-ID: a84b4c76e66710@pc33.atlanta.com
            CSeq: 314159 ACK
            Content-Length: 0""",
            "CANCEL": """CANCEL sip:bob@biloxi.com SIP/2.0
            Via: SIP/2.0/UDP pc33.atlanta.com;branch=z9hG4bKnashds8
            Max-Forwards: 70
            To: Bob <sip:bob@biloxi.com>
            From: Alice <sip:alice@atlanta.com>;tag=1928301774
            Call-ID: a84b4c76e66710@pc33.atlanta.com
            CSeq: 314159 CANCEL
            Content-Length: 0""",
            "OPTIONS": """OPTIONS sip:bob@biloxi.com SIP/2.0
            Via: SIP/2.0/UDP pc33.atlanta.com;branch=z9hG4bKnashds11
            Max-Forwards: 70
            To: <sip:bob@biloxi.com>
            From: Alice <sip:alice@atlanta.com>;tag=1928301774
            Call-ID: a84b4c76e66710
            CSeq: 63104 OPTIONS
            Contact: <sip:alice@pc33.atlanta.com>
            Accept: application/sdp
            Content-Length: 0""",
        }

        return examples.get(message_type, f"No example available for {message_type}")

    async def read_resource(self, uri: str) -> str:
        """Read a documentation file (TXT or PDF)"""
        path = uri.replace("file://", "")
        path_obj = Path(path)

        try:
            if path_obj.suffix == ".pdf":
                return self._extract_pdf_text(path_obj)
            else:
                with open(path, "r") as f:
                    return f.read()
        except Exception as e:
            return f"Error reading resource: {str(e)}"


# Keep WeatherServer class as before...
class WeatherServer(MCPServer):
    """MCP server for weather data"""

    def __init__(self):
        super().__init__(name="weather", description="Get current weather information")

    def get_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "get_weather",
                "description": "Get current weather for a location using Open-Meteo API",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "latitude": {
                            "type": "number",
                            "description": "Latitude coordinate",
                        },
                        "longitude": {
                            "type": "number",
                            "description": "Longitude coordinate",
                        },
                        "location_name": {
                            "type": "string",
                            "description": "Human-readable location name (optional)",
                        },
                    },
                    "required": ["latitude", "longitude"],
                },
            }
        ]

    def get_resources(self) -> List[Dict[str, Any]]:
        return []

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        if tool_name == "get_weather":
            return await self._get_weather(
                arguments["latitude"],
                arguments["longitude"],
                arguments.get("location_name", "Unknown"),
            )
        return {"error": f"Unknown tool: {tool_name}"}

    async def _get_weather(
        self, lat: float, lon: float, location: str
    ) -> Dict[str, Any]:
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": lat,
                        "longitude": lon,
                        "current": "temperature_2m,relative_humidity_2m,wind_speed_10m",
                        "temperature_unit": "celsius",
                    },
                )

                if response.status_code == 200:
                    data = response.json()
                    current = data.get("current", {})

                    return {
                        "location": location,
                        "temperature": f"{current.get('temperature_2m')}°C",
                        "humidity": f"{current.get('relative_humidity_2m')}%",
                        "wind_speed": f"{current.get('wind_speed_10m')} km/h",
                        "coordinates": {"lat": lat, "lon": lon},
                    }
                else:
                    return {"error": f"API error: {response.status_code}"}

        except Exception as e:
            return {"error": f"Failed to fetch weather: {str(e)}"}
