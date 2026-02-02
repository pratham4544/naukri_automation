// background.js - Background service worker

console.log('🤖 Job Auto Apply: Background service worker started');

// Listen for tab updates to detect page loads
chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete') {
    console.log('📄 Page loaded:', tab.url);
  }
});

// Handle messages from content scripts
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  console.log('📨 Message received:', request);
  
  if (request.action === 'jobCompleted') {
    // Move to next job
    handleJobCompletion();
  }
  
  return true;
});

async function handleJobCompletion() {
  const { jobs = [], currentJobIndex = 0, isRunning = false } = 
    await chrome.storage.local.get(['jobs', 'currentJobIndex', 'isRunning']);
  
  if (!isRunning) return;
  
  // Mark current as completed
  if (currentJobIndex < jobs.length) {
    jobs[currentJobIndex].status = 'completed';
  }
  
  const nextIndex = currentJobIndex + 1;
  
  await chrome.storage.local.set({ 
    jobs, 
    currentJobIndex: nextIndex 
  });
  
  // If more jobs, navigate to next
  if (nextIndex < jobs.length) {
    const nextJob = jobs[nextIndex];
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    await chrome.tabs.update(tab.id, { url: nextJob.url });
  } else {
    // All done
    await chrome.storage.local.set({ isRunning: false });
    console.log('✅ All jobs completed!');
  }
}
