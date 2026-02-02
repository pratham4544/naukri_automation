# 🚫 Skip Domains Configuration

## What It Does

Some job sites like **Naukri.com** have their own auto-fill systems that conflict with the extension. For these sites, the extension:

✅ **Skips auto-fill** - Doesn't fill the form
✅ **Watches for submission** - Detects when you submit
✅ **Auto-advances** - Moves to next job automatically

## Currently Skipped Sites

### Naukri.com
- **Why:** Has built-in profile auto-fill
- **Behavior:** You apply manually → Extension detects → Auto-advances

### How It Works

1. Extension loads Naukri.com page
2. Shows: "🚫 Naukri.com detected - skipping auto-fill"
3. You click "Apply" and submit manually
4. Extension watches for success messages
5. Detects: "Application sent" or "Applied successfully"
6. Waits 2 seconds
7. Auto-advances to next job

## Success Messages Detected

- "application sent"
- "applied successfully"
- "already applied"

## Adding More Skip Domains

To skip other sites, edit `content.js`:

```javascript
// Add to the check:
if (currentUrl.includes('naukri.com') || 
    currentUrl.includes('linkedin.com') ||
    currentUrl.includes('workday.com')) {
  console.log('🚫 Skipped domain detected');
  setupAutoAdvanceWatcher();
  return;
}
```

## Recommended Skip Domains

### Sites with Built-in Auto-fill:
- ✅ **naukri.com** - Indian job portal
- ⚠️ **linkedin.com** - LinkedIn Jobs (has Easy Apply)
- ⚠️ **indeed.com** - Indeed Apply
- ⚠️ **workday.com** - Enterprise ATS

### Sites That Work Well:
- ✅ **lever.co** - Modern ATS
- ✅ **greenhouse.io** - Popular ATS
- ✅ **factorialhr.pt** - Factorial HR
- ✅ Custom company career pages

## Manual Override

If you want to force-fill a skipped site:
1. Stop the auto-apply mode
2. Click "Fill Current Page" button
3. Extension will fill regardless of domain

## Workflow Example

**Mixed Job List:**
```
Job 1: https://company-a.com/apply           → Auto-fills
Job 2: https://www.naukri.com/job/12345      → Manual, auto-advances
Job 3: https://company-b.lever.co/apply      → Auto-fills
Job 4: https://www.naukri.com/job/67890      → Manual, auto-advances
```

**Process:**
1. Load all 4 jobs
2. Click "Start Applying"
3. Job 1: Auto-fills → Submit → Next
4. Job 2: Manual apply → Auto-advances
5. Job 3: Auto-fills → Submit → Next
6. Job 4: Manual apply → Auto-advances

## Benefits

✅ **No Conflicts** - Avoids breaking site's auto-fill
✅ **Seamless Flow** - Auto-advances keep you in flow
✅ **Best of Both** - Use site's features + automation
✅ **Faster** - Don't wait for extension on sites with auto-fill

## Customization

### Change Watch Interval

Default: Checks every 2 seconds

```javascript
// In setupNaukriWatcher(), change:
const checkInterval = setInterval(() => {
  // ...
}, 2000); // 2 seconds → change to 1000 for 1 second
```

### Change Watch Duration

Default: Stops after 5 minutes

```javascript
setTimeout(() => {
  clearInterval(checkInterval);
}, 300000); // 5 min → change to 600000 for 10 min
```

### Add Custom Success Messages

```javascript
if (bodyText.includes('application sent') || 
    bodyText.includes('applied successfully') ||
    bodyText.includes('already applied') ||
    bodyText.includes('your custom message')) { // Add here
  // ...
}
```

## Troubleshooting

**Not auto-advancing after Naukri submit?**
- Check console (F12) for "✅ Naukri application detected"
- Verify success message appears on page
- Wait up to 5 minutes (watch timeout)
- Click "Next Job" manually if needed

**Want to disable skip for Naukri?**
Comment out the check in `content.js`:
```javascript
// if (currentUrl.includes('naukri.com')) {
//   setupNaukriWatcher();
//   return;
// }
```

**Other site needs skipping?**
Add domain to the list and create watcher with appropriate success messages.

---

**Smart automation that adapts to each site! 🎯**
