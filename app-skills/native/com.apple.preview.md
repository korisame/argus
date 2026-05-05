---
bundle_id: com.apple.Preview
name: Preview (Anteprima)
---

# Preview / Anteprima

## Surface
Native. PDF/image viewer. Some operations only available via UI; others via AppleScript.

## Open a file
```applescript
tell application "Preview" to open POSIX file "/Users/shaun/Documents/file.pdf"
```

## Annotation toolbar
1. Open Markup toolbar: View → Show Markup Toolbar (Cmd+Shift+A)
2. Tools (left to right, typical layout): Selection, Sketch, Shapes, Text, Sign, Annotate, Adjust Color, Adjust Size, Markup
3. Use vision for tool icons — they are unlabeled. Examples:
   - "the signature icon in the markup toolbar"
   - "the text box icon"
   - "the highlight color picker"

## Sign
1. Click the signature icon (looks like a cursive 'S').
2. Pick existing signature OR "Create Signature" → Trackpad/Camera/iPhone.
3. Drag the placed signature to position. Use `argus_run` for click→drag macro:

```python
from argus import click, see
import time
# Place signature
click("the signature icon in the markup toolbar")
time.sleep(0.5)
click("Shaun signature")  # or whichever pre-saved sig
time.sleep(0.5)
# Now drag — vision-grounded, low confidence; verify after
```

## Page navigation
- Cmd+Right / Cmd+Left: next / prev page
- Cmd+G: go to page

## Don't
- Don't try to fill PDF form fields with `argus_click` — use the dedicated `pdf-viewer` plugin (`pdf-viewer:fill-form`).
- Annotations placed via vision drift on retina/non-retina mix; verify with screenshot after each placement.
