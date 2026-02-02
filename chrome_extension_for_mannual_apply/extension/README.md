# 🤖 Job Auto Apply Chrome Extension

Semi-automatic job application assistant with Q&A memory.

## Features

✅ **CSV Job Loading** - Paste jobs in CSV format
✅ **Q&A Memory** - Saves your answers, never ask twice
✅ **Smart Form Filling** - Auto-fills based on memory
✅ **Dropdown Matching** - Intelligently selects best option
✅ **Semi-Automatic** - You control when to submit
✅ **Progress Tracking** - See how many jobs completed
✅ **Export/Import Memory** - Backup your Q&A data

## Installation

1. **Download/Clone** this extension folder

2. **Open Chrome Extensions**
   - Go to `chrome://extensions/`
   - Enable "Developer mode" (top right)

3. **Load Extension**
   - Click "Load unpacked"
   - Select the `extension` folder

4. **Pin Extension**
   - Click the puzzle icon in Chrome toolbar
   - Pin "Job Auto Apply Assistant"

## Usage

### Step 1: Load Jobs

1. Click the extension icon
2. Paste CSV in this format:
```csv
name,url
AI Engineer - Company A,https://company-a.com/apply
ML Engineer - Company B,https://company-b.com/jobs
```
3. Click "Load Jobs"

### Step 2: Start Applying

1. Click "Start Applying"
2. Extension opens first job URL
3. Waits 3 seconds for page load
4. Auto-clicks "Apply" button if found
5. Fills form using memory
6. **Asks you** for any new questions
7. **You review and submit** manually

### Step 3: Next Job

After submitting current job:
1. Click "Next Job" button
2. Extension moves to next URL
3. Repeat process

## Manual Controls

- **Fill Current Page** - Fill form on active tab
- **Next Job** - Skip to next job in queue
- **Stop** - Pause auto-apply mode

## Memory Management

- **View Memory** - See saved Q&A pairs
- **Export Memory** - Download `qa_memory.json`
- **Import Memory** - Load existing memory file

## Tips

### Prepare Memory File

Before starting, import your `qa_memory.json`:

```json
{
  "first name": "Prathamesh",
  "email": "your@email.com",
  "phone": "1234567890",
  "experience": "2-3 years"
}
```

### For Dropdowns

Answer with the exact option text or partial match:
- Question: "Years of experience"
- Options: "0-1 years", "1-2 years", "2-3 years"
- Answer: "2-3" (will match "2-3 years")

### File Uploads

File uploads require manual action (Chrome security limitation).

## Workflow

1. Load 10-20 jobs via CSV
2. Click "Start Applying"
3. Extension auto-fills each form
4. You review and submit
5. Click "Next Job" after each submission
6. Memory grows with each job
7. Future jobs fill faster

## Privacy

- All data stored locally in Chrome
- No data sent to external servers
- Memory synced with Chrome account (optional)

## Troubleshooting

**Extension not working?**
- Check if site allows extensions
- Refresh page after installing
- Check console for errors (F12)

**Fields not filling?**
- Check if field labels match memory
- Use "Fill Current Page" manually
- Check memory with "View Memory"

**Dropdown not selecting?**
- Answer must match option text
- Try exact option text
- Try partial match (e.g., "2-3" for "2-3 years")

## Files Structure

```
extension/
├── manifest.json       # Extension config
├── popup.html         # UI interface
├── popup.js           # UI logic
├── content.js         # Form filling logic
├── background.js      # Background worker
└── icon*.png          # Extension icons
```

## Development

To modify:
1. Edit files in `extension/` folder
2. Go to `chrome://extensions/`
3. Click "Reload" on your extension
4. Test changes

## Export Your Memory

After applying to 10+ jobs:
1. Click "Export Memory"
2. Save `qa_memory.json`
3. Share with friends or backup
4. Import on new Chrome profile

---

**Made with ❤️ for job seekers**
