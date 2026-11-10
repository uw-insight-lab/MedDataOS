# Imaging specialist

The imaging specialist ranks the case's series against the question, renders one preview slice, and describes that slice with a vision model. It is a stand-in until a fuller imaging agent exists. Any endpoint that answers the same way can replace it.

```bash
pixi run imaging --case /path/to/case
```

It prints `http://127.0.0.1:8003/v1`. Register it beside notes:

```toml
[imaging]
url = "http://127.0.0.1:8003/v1"
description = "Looks at one DICOM slice. Use this for questions about the images, scans, contours, or what is visible on imaging."
```

A confident pick becomes one citation for the series file, tagged `imaging`, with a `preview` of the slice index, window, and overlay. The page loads that slice from `/api/dicom/preview`. Contours are drawn for an RTSTRUCT, or when the question asks for them. If no series ranks confidently, the reply is plain text listing the candidates and has no citation.

The router calls it as `consult_imaging`, at most once per question. The server puts the specialist's preview back on the router's citation for the same file. The contract is in [Connect an agent](../agents.md#imaging-specialist-stand-in).

It reads `GEMINI_API_KEY`, or the Azure settings, from `.env`. An Azure deployment used for imaging has to accept images.
