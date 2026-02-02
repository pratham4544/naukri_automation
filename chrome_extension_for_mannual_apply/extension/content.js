// content.js - Runs on every page

console.log('🤖 Job Auto Apply: Content script loaded');

// Listen for messages from popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'fillForm') {
    fillFormWithMemory().then(result => {
      sendResponse(result);
    });
    return true; // Keep channel open for async response
  }
  
  if (request.action === 'clickApply') {
    clickApplyButton().then(result => {
      sendResponse(result);
    });
    return true;
  }
  
  if (request.action === 'submitForm') {
    submitForm().then(result => {
      sendResponse(result);
    });
    return true;
  }
});

// Auto-detect when page loads if we're in active mode
chrome.storage.local.get(['isRunning'], (result) => {
  if (result.isRunning) {
    const currentUrl = window.location.href;
    
    // For Naukri, wait longer and handle sidebar
    if (currentUrl.includes('naukri.com')) {
      console.log('🔵 Naukri.com detected - handling with sidebar support');
      setTimeout(() => {
        autoProcessNaukri();
      }, 5000); // Wait 5 seconds for Naukri
      return;
    }
    
    console.log('🤖 Active mode detected, waiting 3 seconds...');
    setTimeout(() => {
      autoProcess();
    }, 3000);
  }
});

async function autoProcessNaukri() {
  console.log('🤖 Auto-processing Naukri...');
  
  // Try to click apply button
  const applyResult = await clickApplyButton();
  if (applyResult.success) {
    console.log('✅ Apply button clicked, waiting for sidebar...');
    await sleep(4000);
  }
  
  // Handle Naukri sidebar questions
  await handleNaukriSidebar();
  
  // Check for success and auto-advance
  const bodyText = document.body.innerText.toLowerCase();
  if (bodyText.includes('application sent') || 
      bodyText.includes('applied successfully') ||
      bodyText.includes('already applied')) {
    
    console.log('✅ Naukri application complete, moving to next job...');
    await sleep(2000);
    chrome.runtime.sendMessage({ action: 'jobCompleted' });
  } else {
    alert('⚠️ Please complete the Naukri application manually, then click "Next Job"');
  }
}

async function handleNaukriSidebar() {
  console.log('📋 Looking for Naukri sidebar questions...');
  
  // Get memory
  const { qaMemory = {} } = await chrome.storage.local.get('qaMemory');
  
  let maxAttempts = 20;
  let attempt = 0;
  
  while (attempt < maxAttempts) {
    attempt++;
    console.log(`Attempt ${attempt}/${maxAttempts}`);
    
    await sleep(1000);
    
    // Look for sidebar with questions
    const sidebarData = await findNaukriSidebar();
    
    if (!sidebarData.found) {
      console.log('No sidebar found');
      break;
    }
    
    console.log(`Found sidebar: ${sidebarData.questions.length} questions, ${sidebarData.inputs.length} inputs`);
    
    if (sidebarData.questions.length === 0 || sidebarData.inputs.length === 0) {
      console.log('No questions/inputs in sidebar');
      break;
    }
    
    // Get first question
    const question = sidebarData.questions[0];
    const questionLower = question.toLowerCase().trim();
    
    console.log(`Question: ${question}`);
    
    // Check memory
    let answer = qaMemory[questionLower];
    
    if (!answer) {
      // Ask user
      answer = prompt(`❓ Naukri Question:\n\n${question}`);
      
      if (!answer) {
        console.log('User cancelled or no answer provided');
        break;
      }
      
      // Save to memory
      qaMemory[questionLower] = answer;
      await chrome.storage.local.set({ qaMemory });
      console.log(`💾 Saved to memory: ${questionLower} = ${answer}`);
    } else {
      console.log(`💾 Using from memory: ${answer}`);
    }
    
    // Find input and fill
    const filled = await fillNaukriInput(answer);
    
    if (!filled) {
      console.log('Could not fill input');
      break;
    }
    
    // Click Save/Next button
    const clicked = await clickNaukriSaveButton();
    
    if (!clicked) {
      console.log('Could not find Save button');
      break;
    }
    
    await sleep(2000);
  }
  
  console.log('✅ Finished handling Naukri sidebar');
}

function findNaukriSidebar() {
  const data = {
    found: false,
    questions: [],
    inputs: []
  };
  
  // Look for sidebar containers
  const containers = document.querySelectorAll('[role="dialog"], [class*="drawer"], [class*="sidebar"], [class*="side"], div');
  
  for (const container of containers) {
    const rect = container.getBoundingClientRect();
    
    // Check if it's a wide sidebar
    if (rect.width > 300 && rect.width < window.innerWidth && rect.height > 200) {
      const text = container.innerText;
      const lines = text.split('\n');
      
      // Find questions
      lines.forEach(line => {
        line = line.trim();
        if (line.includes('?') && 
            line.length > 10 && 
            line.length < 300 &&
            !line.includes('http')) {
          if (!data.questions.includes(line)) {
            data.questions.push(line);
          }
        }
      });
      
      // Find inputs
      const inputs = container.querySelectorAll('input:not([type="hidden"]), textarea');
      inputs.forEach(inp => {
        const inpRect = inp.getBoundingClientRect();
        if (inpRect.width > 0 && inpRect.height > 0 && !inp.value) {
          data.inputs.push({
            element: inp,
            type: inp.type || 'text'
          });
        }
      });
      
      if (data.questions.length > 0 || data.inputs.length > 0) {
        data.found = true;
        break;
      }
    }
  }
  
  return data;
}

async function fillNaukriInput(answer) {
  // Find visible empty input in sidebar
  const containers = document.querySelectorAll('[role="dialog"], [class*="drawer"], [class*="sidebar"], [class*="side"], div');
  
  for (const container of containers) {
    const rect = container.getBoundingClientRect();
    
    if (rect.width > 300 && rect.height > 200) {
      const inputs = container.querySelectorAll('input:not([type="hidden"]), textarea');
      
      for (const inp of inputs) {
        const inpRect = inp.getBoundingClientRect();
        if (inpRect.width > 0 && inpRect.height > 0 && !inp.value) {
          try {
            inp.focus();
            inp.click();
            await sleep(300);
            inp.value = answer;
            inp.dispatchEvent(new Event('input', { bubbles: true }));
            inp.dispatchEvent(new Event('change', { bubbles: true }));
            console.log(`✅ Filled input with: ${answer}`);
            return true;
          } catch (err) {
            console.error('Fill error:', err);
          }
        }
      }
    }
  }
  
  return false;
}

async function clickNaukriSaveButton() {
  // Look for Save/Submit/Next button in sidebar
  const containers = document.querySelectorAll('[role="dialog"], [class*="drawer"], [class*="sidebar"], [class*="side"], div');
  
  for (const container of containers) {
    const rect = container.getBoundingClientRect();
    
    if (rect.width > 300) {
      const buttons = container.querySelectorAll('button');
      
      for (const btn of buttons) {
        const text = (btn.innerText || '').toLowerCase();
        if ((text.includes('save') || 
             text.includes('submit') || 
             text.includes('next') ||
             text.includes('continue')) && 
            btn.offsetParent !== null &&
            !btn.disabled) {
          
          console.log(`🖱️ Clicking: ${btn.innerText}`);
          btn.click();
          return true;
        }
      }
    }
  }
  
  return false;
}

function setupNaukriWatcher() {
  console.log('👀 Watching for Naukri submission...');
  
  // Check every 2 seconds for success indicators
  const checkInterval = setInterval(() => {
    const bodyText = document.body.innerText.toLowerCase();
    
    if (bodyText.includes('application sent') || 
        bodyText.includes('applied successfully') ||
        bodyText.includes('already applied')) {
      
      console.log('✅ Naukri application detected, moving to next job...');
      clearInterval(checkInterval);
      
      // Move to next job after 2 seconds
      setTimeout(() => {
        chrome.runtime.sendMessage({ action: 'jobCompleted' });
      }, 2000);
    }
  }, 2000);
  
  // Stop watching after 5 minutes
  setTimeout(() => {
    clearInterval(checkInterval);
  }, 300000);
}

async function autoProcess() {
  console.log('🤖 Auto-processing page...');
  
  // Try to click apply button
  const applyResult = await clickApplyButton();
  if (applyResult.success) {
    console.log('✅ Apply button clicked, waiting for form...');
    await sleep(3000);
  }
  
  // Fill form
  const fillResult = await fillFormWithMemory();
  console.log('📋 Form fill result:', fillResult);
  
  // Check if form is complete
  const emptyRequired = findEmptyRequiredFields();
  
  if (emptyRequired.length === 0) {
    console.log('✅ All required fields filled!');
    
    // Auto-submit after confirmation
    if (confirm('✅ Form filled! Submit now?')) {
      const submitResult = await submitForm();
      
      if (submitResult.success || submitResult.clicked) {
        console.log('✅ Form submitted! Moving to next job in 3 seconds...');
        
        // Wait for success page to load
        await sleep(3000);
        
        // Auto-advance to next job
        chrome.runtime.sendMessage({ action: 'jobCompleted' });
      } else {
        alert('⚠️ Could not find submit button. Please submit manually and click "Next Job".');
      }
    } else {
      alert('Form ready but not submitted. Click "Next Job" when done.');
    }
  } else {
    console.log('⚠️ Some required fields need attention:', emptyRequired);
    alert(`⚠️ Please fill ${emptyRequired.length} required field(s) manually:\n\n${emptyRequired.slice(0, 3).map(f => f.label).join('\n')}\n\nClick "Next Job" when done.`);
  }
}

async function clickApplyButton() {
  const buttons = document.querySelectorAll('button, a, input[type="button"], input[type="submit"]');
  
  for (const btn of buttons) {
    const text = (btn.innerText || btn.value || '').toLowerCase();
    
    if (text.includes('apply') && 
        !text.includes('applied') &&
        btn.offsetParent !== null &&
        !btn.disabled) {
      
      console.log('🖱️ Clicking Apply button:', btn.innerText || btn.value);
      btn.click();
      await sleep(2000);
      
      return { success: true, text: btn.innerText || btn.value };
    }
  }
  
  return { success: false };
}

async function fillFormWithMemory() {
  // Get memory and files from storage
  const { qaMemory = {}, resume, coverLetter } = await chrome.storage.local.get(['qaMemory', 'resume', 'coverLetter']);
  
  // Find all fillable fields
  const fields = findAllFields();
  console.log(`📋 Found ${fields.length} fields`);
  
  let filledCount = 0;
  let askedCount = 0;
  
  for (const field of fields) {
    // Skip if already filled
    if (field.element.value) {
      continue;
    }
    
    const question = (field.label || field.placeholder || field.name || '').toLowerCase().trim();
    
    if (!question) continue;
    
    // Handle file upload
    if (field.type === 'file') {
      console.log('📎 File upload field found:', question);
      
      // Determine if it's resume or cover letter
      const isResume = question.includes('resume') || question.includes('cv');
      const isCoverLetter = question.includes('cover') || question.includes('letter');
      
      if (isResume && resume) {
        try {
          // Create file from base64
          const blob = await fetch(resume.data).then(r => r.blob());
          const file = new File([blob], resume.name, { type: resume.type });
          
          // Create DataTransfer to set files
          const dataTransfer = new DataTransfer();
          dataTransfer.items.add(file);
          field.element.files = dataTransfer.files;
          
          // Trigger change event
          field.element.dispatchEvent(new Event('change', { bubbles: true }));
          
          console.log(`✅ Resume uploaded: ${resume.name}`);
          filledCount++;
        } catch (err) {
          console.error('Resume upload failed:', err);
          
          // Show alert with instruction
          alert(`⚠️ Auto-upload failed for: ${question}\n\nPlease upload manually: ${resume.name}\n\nNote: Some sites block automatic file uploads for security.`);
        }
      } else if (isCoverLetter && coverLetter) {
        try {
          const blob = await fetch(coverLetter.data).then(r => r.blob());
          const file = new File([blob], coverLetter.name, { type: coverLetter.type });
          
          const dataTransfer = new DataTransfer();
          dataTransfer.items.add(file);
          field.element.files = dataTransfer.files;
          field.element.dispatchEvent(new Event('change', { bubbles: true }));
          
          console.log(`✅ Cover Letter uploaded: ${coverLetter.name}`);
          filledCount++;
        } catch (err) {
          console.error('Cover letter upload failed:', err);
          
          alert(`⚠️ Auto-upload failed for: ${question}\n\nPlease upload manually: ${coverLetter.name}`);
        }
      } else {
        // No file available
        console.log('⚠️ No file available for:', question);
        if (field.required) {
          alert(`📎 Please upload file manually:\n${field.label || field.placeholder || 'File upload'}\n\n${isResume ? 'Resume/CV required' : isCoverLetter ? 'Cover Letter required' : 'File upload required'}`);
        }
      }
      continue;
    }
    
    // Check if this is a text field asking for resume/CV path
    // Some forms have text inputs asking for resume filename or path
    if (question.includes('resume') || question.includes('cv')) {
      if (resume && qaMemory[question]) {
        // Use filename from memory
        field.element.value = qaMemory[question];
        field.element.dispatchEvent(new Event('input', { bubbles: true }));
        field.element.dispatchEvent(new Event('change', { bubbles: true }));
        console.log(`✅ Filled resume text: ${question} = ${qaMemory[question]}`);
        filledCount++;
        continue;
      }
    }
    
    if (question.includes('cover') && question.includes('letter')) {
      if (coverLetter && qaMemory[question]) {
        field.element.value = qaMemory[question];
        field.element.dispatchEvent(new Event('input', { bubbles: true }));
        field.element.dispatchEvent(new Event('change', { bubbles: true }));
        console.log(`✅ Filled cover letter text: ${question} = ${qaMemory[question]}`);
        filledCount++;
        continue;
      }
    }
    
    // Check memory
    if (qaMemory[question]) {
      const answer = qaMemory[question];
      
      if (field.tag === 'select') {
        // Handle dropdown
        const matched = selectBestOption(field.element, answer);
        if (matched) {
          console.log(`✅ Selected: ${question} = ${answer}`);
          filledCount++;
        }
      } else {
        // Fill text field
        field.element.value = answer;
        field.element.dispatchEvent(new Event('input', { bubbles: true }));
        field.element.dispatchEvent(new Event('change', { bubbles: true }));
        console.log(`✅ Filled: ${question} = ${answer}`);
        filledCount++;
      }
    } else if (field.required) {
      // Ask user for required fields
      const answer = prompt(`❓ Required: ${field.label || field.placeholder || field.name}`);
      
      if (answer) {
        if (field.tag === 'select') {
          selectBestOption(field.element, answer);
        } else {
          field.element.value = answer;
          field.element.dispatchEvent(new Event('input', { bubbles: true }));
          field.element.dispatchEvent(new Event('change', { bubbles: true }));
        }
        
        // Save to memory
        qaMemory[question] = answer;
        await chrome.storage.local.set({ qaMemory });
        
        filledCount++;
        askedCount++;
      }
    }
  }
  
  console.log(`✅ Filled ${filledCount} fields (${askedCount} asked)`);
  
  return { 
    success: true, 
    filledCount, 
    askedCount,
    totalFields: fields.length 
  };
}

function findAllFields() {
  const fields = [];
  const elements = document.querySelectorAll('input, textarea, select');
  
  elements.forEach(el => {
    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    
    // Check if visible
    if (rect.width > 0 && 
        rect.height > 0 && 
        style.display !== 'none' && 
        style.visibility !== 'hidden' &&
        el.type !== 'hidden' &&
        el.type !== 'submit' &&
        el.type !== 'button' &&
        el.type !== 'image') {
      
      // Get label
      let label = '';
      if (el.labels && el.labels.length > 0) {
        label = el.labels[0].innerText.trim();
      } else if (el.id) {
        const labelEl = document.querySelector(`label[for="${el.id}"]`);
        if (labelEl) label = labelEl.innerText.trim();
      }
      
      fields.push({
        element: el,
        tag: el.tagName.toLowerCase(),
        type: el.type || 'text',
        name: el.name || '',
        id: el.id || '',
        label: label,
        placeholder: el.placeholder || '',
        required: el.required || el.hasAttribute('required')
      });
    }
  });
  
  return fields;
}

function selectBestOption(selectElement, answer) {
  const options = Array.from(selectElement.options);
  
  // Try exact match
  for (const opt of options) {
    if (opt.text.toLowerCase() === answer.toLowerCase()) {
      selectElement.value = opt.value;
      selectElement.dispatchEvent(new Event('change', { bubbles: true }));
      return true;
    }
  }
  
  // Try partial match
  for (const opt of options) {
    if (opt.text.toLowerCase().includes(answer.toLowerCase()) ||
        answer.toLowerCase().includes(opt.text.toLowerCase())) {
      selectElement.value = opt.value;
      selectElement.dispatchEvent(new Event('change', { bubbles: true }));
      return true;
    }
  }
  
  return false;
}

function findEmptyRequiredFields() {
  const fields = findAllFields();
  return fields.filter(f => f.required && !f.element.value);
}

async function submitForm() {
  const buttons = document.querySelectorAll('button, input[type="submit"]');
  
  for (const btn of buttons) {
    const text = (btn.innerText || btn.value || '').toLowerCase();
    
    if ((text.includes('submit') || 
         text.includes('apply') || 
         text.includes('send')) &&
        btn.offsetParent !== null &&
        !btn.disabled) {
      
      console.log('📤 Clicking submit:', btn.innerText || btn.value);
      btn.click();
      
      await sleep(3000);
      
      // Check for success
      const bodyText = document.body.innerText.toLowerCase();
      const success = bodyText.includes('thank') || 
                     bodyText.includes('success') || 
                     bodyText.includes('submitted') ||
                     bodyText.includes('received');
      
      return { success, clicked: true };
    }
  }
  
  return { success: false, clicked: false };
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}
