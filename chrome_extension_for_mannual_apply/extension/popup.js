// popup.js - Main popup logic

let jobs = [];
let currentJobIndex = 0;
let isRunning = false;

// Load stats on popup open
document.addEventListener('DOMContentLoaded', async () => {
  await updateStats();
  await loadState();
});

// Load Jobs
document.getElementById('loadJobs').addEventListener('click', async () => {
  const csv = document.getElementById('jobsCsv').value.trim();
  
  if (!csv) {
    alert('Please paste CSV data');
    return;
  }
  
  // Parse CSV - handle different formats
  const lines = csv.split('\n').filter(line => line.trim());
  const parsedJobs = [];
  let hasHeader = false;
  
  // Check if first line is header
  const firstLine = lines[0].toLowerCase();
  if (firstLine.includes('name') && firstLine.includes('url')) {
    hasHeader = true;
  }
  
  const startIndex = hasHeader ? 1 : 0;
  
  for (let i = startIndex; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;
    
    // Try to extract URL - look for http/https
    const urlMatch = line.match(/(https?:\/\/[^\s,]+)/);
    
    if (urlMatch) {
      const url = urlMatch[1];
      
      // Get name (everything before URL)
      let name = line.substring(0, line.indexOf(url)).trim();
      // Clean up name - remove trailing commas/brackets
      name = name.replace(/[,\[\]]+$/, '').trim();
      
      if (!name) {
        // Try to extract from URL
        name = url.split('/').filter(p => p).pop() || `Job ${i}`;
      }
      
      // Validate URL
      try {
        new URL(url);
        parsedJobs.push({
          name: name || `Job ${parsedJobs.length + 1}`,
          url: url,
          status: 'pending'
        });
      } catch (e) {
        console.error('Invalid URL:', url);
      }
    }
  }
  
  if (parsedJobs.length === 0) {
    alert('❌ No valid URLs found!\n\nFormat:\nname,url\nAI Engineer,https://example.com/apply\n\nOr just paste URLs (one per line)');
    return;
  }
  
  jobs = parsedJobs;
  currentJobIndex = 0;
  
  // Save to storage
  await chrome.storage.local.set({ jobs, currentJobIndex });
  
  // Show loaded jobs
  let jobsList = `✅ Loaded ${jobs.length} jobs:\n\n`;
  jobs.slice(0, 5).forEach((job, i) => {
    jobsList += `${i+1}. ${job.name}\n`;
  });
  if (jobs.length > 5) {
    jobsList += `... and ${jobs.length - 5} more`;
  }
  
  alert(jobsList);
  await updateStats();
});

// Start Applying
document.getElementById('startApplying').addEventListener('click', async () => {
  if (jobs.length === 0) {
    alert('Please load jobs first!');
    return;
  }
  
  if (currentJobIndex >= jobs.length) {
    alert('All jobs completed! Load new jobs to continue.');
    return;
  }
  
  isRunning = true;
  document.getElementById('startApplying').style.display = 'none';
  document.getElementById('stopApplying').style.display = 'block';
  
  await chrome.storage.local.set({ isRunning: true });
  
  // Navigate to first/next job
  await navigateToCurrentJob();
});

// Stop Applying
document.getElementById('stopApplying').addEventListener('click', async () => {
  isRunning = false;
  await chrome.storage.local.set({ isRunning: false });
  
  document.getElementById('startApplying').style.display = 'block';
  document.getElementById('stopApplying').style.display = 'none';
  
  updateStatus('⏸️ Stopped by user', 'idle');
});

// Fill Current Page
document.getElementById('fillCurrentPage').addEventListener('click', async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  
  chrome.tabs.sendMessage(tab.id, { action: 'fillForm' }, (response) => {
    if (chrome.runtime.lastError) {
      alert('Error: ' + chrome.runtime.lastError.message);
    } else if (response && response.success) {
      alert(`✅ Filled ${response.filledCount} fields!`);
      updateStats();
    }
  });
});

// Next Job
document.getElementById('nextJob').addEventListener('click', async () => {
  if (jobs.length === 0) {
    alert('No jobs loaded');
    return;
  }
  
  // Mark current as completed
  if (currentJobIndex < jobs.length) {
    jobs[currentJobIndex].status = 'completed';
  }
  
  currentJobIndex++;
  await chrome.storage.local.set({ jobs, currentJobIndex });
  
  if (currentJobIndex < jobs.length) {
    await navigateToCurrentJob();
  } else {
    alert('✅ All jobs completed!');
    updateStatus('✅ All jobs completed', 'success');
  }
});

// View Memory
document.getElementById('viewMemory').addEventListener('click', async () => {
  const { qaMemory = {} } = await chrome.storage.local.get('qaMemory');
  
  const count = Object.keys(qaMemory).length;
  
  if (count === 0) {
    alert('Memory is empty. Fill some forms to build memory!');
    return;
  }
  
  // Show first 10 items
  const items = Object.entries(qaMemory).slice(0, 10);
  let display = `Memory (${count} items):\n\n`;
  
  items.forEach(([q, a]) => {
    display += `Q: ${q}\nA: ${a}\n\n`;
  });
  
  if (count > 10) {
    display += `... and ${count - 10} more items`;
  }
  
  alert(display);
});

// Export Memory
document.getElementById('exportMemory').addEventListener('click', async () => {
  const { qaMemory = {} } = await chrome.storage.local.get('qaMemory');
  
  const json = JSON.stringify(qaMemory, null, 2);
  const blob = new Blob([json], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  
  const a = document.createElement('a');
  a.href = url;
  a.download = 'qa_memory.json';
  a.click();
  
  alert('✅ Memory exported!');
});

// Import Memory
document.getElementById('importMemory').addEventListener('click', () => {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = '.json';
  
  input.onchange = async (e) => {
    const file = e.target.files[0];
    const text = await file.text();
    
    try {
      const imported = JSON.parse(text);
      
      // Merge with existing
      const { qaMemory = {} } = await chrome.storage.local.get('qaMemory');
      const merged = { ...qaMemory, ...imported };
      
      await chrome.storage.local.set({ qaMemory: merged });
      
      alert(`✅ Imported ${Object.keys(imported).length} items!`);
      await updateStats();
    } catch (err) {
      alert('Error importing: ' + err.message);
    }
  };
  
  input.click();
});

// Upload Resume
document.getElementById('uploadResume').addEventListener('click', () => {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = '.pdf,.doc,.docx';
  
  input.onchange = async (e) => {
    const file = e.target.files[0];
    
    if (!file) return;
    
    // Convert to base64
    const reader = new FileReader();
    reader.onload = async (event) => {
      const base64 = event.target.result;
      
      await chrome.storage.local.set({ 
        resume: {
          name: file.name,
          data: base64,
          type: file.type,
          size: file.size
        }
      });
      
      // Auto-update ALL resume/CV entries in memory
      const { qaMemory = {} } = await chrome.storage.local.get('qaMemory');
      
      const resumeKeys = [
        'resume', 'resume *', 'cv', 'cv *', 'upload resume', 'upload cv',
        'attach resume', 'attach cv', 'resume/cv', 'resume / cv', 'resumecv',
        'resume file', 'cv file', 'resume (pdf)', 'cv (pdf)', 'resume *',
        'cv *', 'attach resume *', 'attach cv *'
      ];
      
      resumeKeys.forEach(key => {
        qaMemory[key] = file.name;
      });
      
      await chrome.storage.local.set({ qaMemory });
      
      console.log(`✅ Updated ${resumeKeys.length} resume entries in memory`);
      alert(`✅ Resume uploaded: ${file.name}\n\n💾 Auto-updated ${resumeKeys.length} memory entries`);
      await updateStats();
      await updateFileStatus();
    };
    
    reader.readAsDataURL(file);
  };
  
  input.click();
});

// Upload Cover Letter
document.getElementById('uploadCoverLetter').addEventListener('click', () => {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = '.pdf,.doc,.docx,.txt';
  
  input.onchange = async (e) => {
    const file = e.target.files[0];
    
    if (!file) return;
    
    // Convert to base64
    const reader = new FileReader();
    reader.onload = async (event) => {
      const base64 = event.target.result;
      
      await chrome.storage.local.set({ 
        coverLetter: {
          name: file.name,
          data: base64,
          type: file.type,
          size: file.size
        }
      });
      
      // Auto-update ALL cover letter entries in memory
      const { qaMemory = {} } = await chrome.storage.local.get('qaMemory');
      
      const coverLetterKeys = [
        'cover letter', 'cover letter *', 'coverletter', 'upload cover letter',
        'attach cover letter', 'cover letter file', 'cover letter (pdf)',
        'attach cover letter *'
      ];
      
      coverLetterKeys.forEach(key => {
        qaMemory[key] = file.name;
      });
      
      await chrome.storage.local.set({ qaMemory });
      
      console.log(`✅ Updated ${coverLetterKeys.length} cover letter entries in memory`);
      alert(`✅ Cover Letter uploaded: ${file.name}\n\n💾 Auto-updated ${coverLetterKeys.length} memory entries`);
      await updateStats();
      await updateFileStatus();
    };
    
    reader.readAsDataURL(file);
  };
  
  input.click();
});

// Helper Functions
async function navigateToCurrentJob() {
  if (currentJobIndex >= jobs.length) {
    updateStatus('✅ All jobs completed', 'success');
    return;
  }
  
  const job = jobs[currentJobIndex];
  
  updateStatus(`📋 Opening: ${job.name}`, 'working');
  document.getElementById('currentJob').style.display = 'block';
  document.getElementById('jobUrl').textContent = job.url;
  document.getElementById('jobUrl').href = job.url;
  document.getElementById('progress').style.display = 'block';
  
  updateProgress();
  
  // Open in current tab
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  await chrome.tabs.update(tab.id, { url: job.url });
}

async function updateStats() {
  const { qaMemory = {}, jobs: savedJobs = [] } = await chrome.storage.local.get(['qaMemory', 'jobs']);
  
  document.getElementById('memoryCount').textContent = Object.keys(qaMemory).length;
  
  const completed = savedJobs.filter(j => j.status === 'completed').length;
  document.getElementById('appliedCount').textContent = completed;
  
  await updateFileStatus();
}

async function updateFileStatus() {
  const { resume, coverLetter } = await chrome.storage.local.get(['resume', 'coverLetter']);
  
  if (resume) {
    document.getElementById('resumeStatus').textContent = `📎 Resume: ${resume.name} (${formatFileSize(resume.size)})`;
    document.getElementById('resumeStatus').style.color = '#48bb78';
  } else {
    document.getElementById('resumeStatus').textContent = '📎 Resume: Not uploaded';
    document.getElementById('resumeStatus').style.color = '#718096';
  }
  
  if (coverLetter) {
    document.getElementById('coverLetterStatus').textContent = `📎 Cover Letter: ${coverLetter.name} (${formatFileSize(coverLetter.size)})`;
    document.getElementById('coverLetterStatus').style.color = '#48bb78';
  } else {
    document.getElementById('coverLetterStatus').textContent = '📎 Cover Letter: Not uploaded';
    document.getElementById('coverLetterStatus').style.color = '#718096';
  }
}

function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

async function loadState() {
  const { jobs: savedJobs = [], currentJobIndex: savedIndex = 0, isRunning: savedRunning = false } = 
    await chrome.storage.local.get(['jobs', 'currentJobIndex', 'isRunning']);
  
  jobs = savedJobs;
  currentJobIndex = savedIndex;
  isRunning = savedRunning;
  
  if (isRunning && jobs.length > 0) {
    document.getElementById('startApplying').style.display = 'none';
    document.getElementById('stopApplying').style.display = 'block';
    
    if (currentJobIndex < jobs.length) {
      const job = jobs[currentJobIndex];
      updateStatus(`📋 Current: ${job.name}`, 'working');
      document.getElementById('currentJob').style.display = 'block';
      document.getElementById('jobUrl').textContent = job.url;
      document.getElementById('jobUrl').href = job.url;
      document.getElementById('progress').style.display = 'block';
      updateProgress();
    }
  }
}

function updateStatus(message, type) {
  const statusEl = document.getElementById('status');
  statusEl.textContent = message;
  statusEl.className = 'status status-' + type;
}

function updateProgress() {
  if (jobs.length === 0) return;
  
  const percent = ((currentJobIndex + 1) / jobs.length) * 100;
  document.getElementById('progressFill').style.width = percent + '%';
  document.getElementById('progressText').textContent = `${currentJobIndex + 1} / ${jobs.length}`;
}
