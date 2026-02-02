from playwright.async_api import async_playwright
import asyncio
import json
import os
import csv
from datetime import datetime

class JobApplyBot:
    def __init__(self):
        self.qa_file = 'qa_memory.json'
        self.qa_memory = self.load_memory()
        self.resume_path = 'Prathamesh_Resume.pdf'
        
    def load_memory(self):
        if os.path.exists(self.qa_file):
            with open(self.qa_file, 'r') as f:
                return json.load(f)
        return {}
    
    def save_memory(self):
        with open(self.qa_file, 'w') as f:
            json.dump(self.qa_memory, f, indent=2)
    
    def get_answer(self, question, field_type='text'):
        q = question.lower().strip()
        
        if q in self.qa_memory:
            ans = self.qa_memory[q]
            print(f"  💾 Memory: {ans}")
            return ans
        
        print(f"\n  ❓ NEW: {question}")
        print(f"     Type: {field_type}")
        answer = input(f"  Answer: ").strip()
        
        if answer:
            self.qa_memory[q] = answer
            self.save_memory()
            print(f"  ✅ Saved!")
        
        return answer
    
    def should_skip_url(self, url):
        skip_domains = [
            'myworkdayjobs.com',
            'workday.com',
            'greenhouse.io',
            'lever.co',
            'naukri.com',
            'linkedin.com',
            'indeed.com'
        ]
        
        url_lower = url.lower()
        for domain in skip_domains:
            if domain in url_lower:
                return True, domain
        return False, None

async def scrape_page_info(page, url):
    """Scrape all page information for understanding"""
    
    print("\n  📸 Scraping page info...")
    
    info = await page.evaluate('''() => {
        const data = {
            title: document.title,
            url: window.location.href,
            forms: [],
            buttons: [],
            links: [],
            text_content: []
        };
        
        // Get all forms
        document.querySelectorAll('form').forEach((form, idx) => {
            const formData = {
                index: idx,
                action: form.action || '',
                method: form.method || '',
                fields: []
            };
            
            form.querySelectorAll('input, textarea, select').forEach(field => {
                if (field.type !== 'hidden') {
                    formData.fields.push({
                        type: field.type || field.tagName.toLowerCase(),
                        name: field.name || '',
                        id: field.id || '',
                        placeholder: field.placeholder || '',
                        required: field.required || field.hasAttribute('required')
                    });
                }
            });
            
            data.forms.push(formData);
        });
        
        // Get all buttons
        document.querySelectorAll('button, input[type="button"], input[type="submit"]').forEach(btn => {
            if (btn.offsetParent !== null) {
                data.buttons.push({
                    text: btn.innerText || btn.value || '',
                    type: btn.type || '',
                    disabled: btn.disabled
                });
            }
        });
        
        // Get key links
        document.querySelectorAll('a').forEach(link => {
            const text = link.innerText.trim().toLowerCase();
            if (text.includes('apply') || text.includes('career') || text.includes('job')) {
                data.links.push({
                    text: link.innerText.trim(),
                    href: link.href
                });
            }
        });
        
        // Get headings and important text
        document.querySelectorAll('h1, h2, h3, p').forEach(el => {
            const text = el.innerText.trim();
            if (text.length > 10 && text.length < 200) {
                data.text_content.push(text);
            }
        });
        
        return data;
    }''')
    
    # Save to file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"scraped_{timestamp}.json"
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(info, f, indent=2, ensure_ascii=False)
    
    print(f"  ✅ Page info saved to: {filename}")
    print(f"     Forms: {len(info['forms'])}")
    print(f"     Buttons: {len(info['buttons'])}")
    print(f"     Links: {len(info['links'])}")
    
    return info

async def find_form_fields(page):
    fields = await page.evaluate('''() => {
        const fields = [];
        const elements = document.querySelectorAll('input, textarea, select');
        
        elements.forEach((el, idx) => {
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            
            if (rect.width > 0 && rect.height > 0 && 
                style.display !== 'none' && 
                style.visibility !== 'hidden' &&
                el.type !== 'hidden' &&
                el.type !== 'submit' &&
                el.type !== 'button' &&
                el.type !== 'image') {
                
                let label = '';
                if (el.labels && el.labels.length > 0) {
                    label = el.labels[0].innerText.trim();
                } else if (el.placeholder) {
                    label = el.placeholder;
                } else if (el.name) {
                    label = el.name;
                } else if (el.id) {
                    const labelEl = document.querySelector(`label[for="${el.id}"]`);
                    if (labelEl) label = labelEl.innerText.trim();
                }
                
                const isRequired = el.required || el.hasAttribute('required') || 
                                 el.getAttribute('aria-required') === 'true';
                
                fields.push({
                    index: idx,
                    tag: el.tagName.toLowerCase(),
                    type: el.type || 'text',
                    name: el.name || '',
                    id: el.id || '',
                    label: label,
                    placeholder: el.placeholder || '',
                    value: el.value || '',
                    required: isRequired
                });
            }
        });
        
        return fields;
    }''')
    
    return fields

async def check_form_validation(page):
    """Check if form has validation errors"""
    
    errors = await page.evaluate('''() => {
        const errors = [];
        
        // Check for error messages
        const errorSelectors = [
            '[class*="error"]',
            '[class*="invalid"]',
            '[aria-invalid="true"]',
            '.error-message',
            '.validation-error'
        ];
        
        errorSelectors.forEach(selector => {
            document.querySelectorAll(selector).forEach(el => {
                if (el.offsetParent !== null && el.innerText.trim()) {
                    errors.push(el.innerText.trim());
                }
            });
        });
        
        // Check for required empty fields
        document.querySelectorAll('input[required], textarea[required], select[required]').forEach(field => {
            if (!field.value && field.offsetParent !== null) {
                const label = field.labels?.[0]?.innerText || field.placeholder || field.name;
                errors.push(`Required field empty: ${label}`);
            }
        });
        
        return errors;
    }''')
    
    return errors

async def main():
    input_file = 'jobs.csv'
    output_file = f'results_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    
    if not os.path.exists(input_file):
        print(f"❌ {input_file} not found! Creating sample...")
        with open(input_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['name', 'url'])
            writer.writerow(['AI Engineer - Opplane', 'https://opplane.factorialhr.pt/apply/ai-engineer-279754'])
        print(f"✅ Created {input_file}")
        return
    
    jobs = []
    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        jobs = list(reader)
    
    print(f"📋 Loaded {len(jobs)} jobs")
    
    bot = JobApplyBot()
    output_data = []
    
    async with async_playwright() as p:
        print("="*80)
        print("JOB AUTO-APPLY BOT")
        print("="*80)
        
        browser = await p.chromium.launch(headless=False, args=['--start-maximized'])
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080}, 
            no_viewport=True
        )
        page = await context.new_page()
        
        for i, job in enumerate(jobs, 1):
            job_name = job.get('name', '').strip()
            url = job.get('url', '').strip()
            
            print(f"\n{'='*80}")
            print(f"  [{i}/{len(jobs)}] {job_name}")
            print(f"  {url}")
            print(f"{'='*80}")
            
            result = {
                'name': job_name,
                'url': url,
                'status': '',
                'fields_found': 0,
                'fields_filled': 0,
                'submitted': 'No',
                'error': '',
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            if not url:
                print("  ⚠️  Empty URL")
                result['status'] = 'Empty URL'
                output_data.append(result)
                continue
            
            should_skip, skip_reason = bot.should_skip_url(url)
            if should_skip:
                print(f"  ⏭️  Skipped - Requires login ({skip_reason})")
                result['status'] = f'Requires Login ({skip_reason})'
                output_data.append(result)
                continue
            
            try:
                print(f"\n  🌐 Opening...")
                await page.goto(url, timeout=60000, wait_until='domcontentloaded')
                await asyncio.sleep(4)
                
                # Scrape page info
                page_info = await scrape_page_info(page, url)
                
                # Check for Apply button
                print("\n  🔍 Looking for Apply button...")
                apply_clicked = await page.evaluate('''() => {
                    const buttons = document.querySelectorAll('button, a, input[type="button"]');
                    
                    for (const btn of buttons) {
                        const text = btn.innerText || btn.value || '';
                        const textLower = text.toLowerCase();
                        
                        if (textLower.includes('apply') && 
                            !textLower.includes('applied') &&
                            btn.offsetParent !== null &&
                            !btn.disabled) {
                            btn.click();
                            return {success: true, text: text};
                        }
                    }
                    return {success: false};
                }''')
                
                if apply_clicked['success']:
                    print(f"  ✅ Clicked Apply: {apply_clicked['text']}")
                    await asyncio.sleep(3)
                else:
                    print("  ℹ️  No Apply button (direct form)")
                
                # Find form fields
                print("\n  🔍 Finding fields...")
                fields = await find_form_fields(page)
                
                result['fields_found'] = len(fields)
                
                if not fields:
                    print("  ⚠️  No form found")
                    result['status'] = 'No Form Found'
                    output_data.append(result)
                    
                    # Ask user
                    action = input("\n  🤔 No form found. Options:\n     1. Skip\n     2. Wait for manual action\n  Choose (1/2): ").strip()
                    if action == '2':
                        input("  ⏸️  Fill manually and press ENTER when done...")
                        result['status'] = 'Manual Fill'
                        result['submitted'] = 'Manual'
                    
                    continue
                
                print(f"  📋 Found {len(fields)} fields")
                
                required_fields = [f for f in fields if f['required']]
                print(f"  📝 Required: {len(required_fields)}, Optional: {len(fields) - len(required_fields)}")
                
                for field in fields[:5]:
                    label = field['label'] or field['placeholder'] or field['name']
                    req = '*' if field['required'] else ''
                    print(f"     - {label} ({field['type']}) {req}")
                
                filled_count = 0
                stuck_fields = []
                
                # Fill each field
                for field in fields:
                    try:
                        if field['value']:
                            continue
                        
                        question = field['label'] or field['placeholder'] or field['name'] or f"Field {field['index']}"
                        
                        # Handle file upload
                        if field['type'] == 'file':
                            if os.path.exists(bot.resume_path):
                                selector = f'input[type="file"]'
                                if field['id']:
                                    selector = f'#{field["id"]}'
                                elif field['name']:
                                    selector = f'input[name="{field["name"]}"]'
                                
                                try:
                                    await page.set_input_files(selector, bot.resume_path)
                                    print(f"  ✅ Resume uploaded")
                                    filled_count += 1
                                except Exception as e:
                                    print(f"  ⚠️  Resume upload failed: {e}")
                                    stuck_fields.append({'field': question, 'error': str(e)})
                            continue
                        
                        # Handle select dropdown
                        if field['tag'] == 'select':
                            answer = bot.get_answer(question, 'select')
                            if not answer:
                                stuck_fields.append({'field': question, 'error': 'No answer provided'})
                                continue
                            
                            selector = f'select'
                            if field['id']:
                                selector = f'#{field["id"]}'
                            elif field['name']:
                                selector = f'select[name="{field["name"]}"]'
                            
                            try:
                                await page.select_option(selector, label=answer)
                                filled_count += 1
                            except:
                                try:
                                    await page.select_option(selector, value=answer)
                                    filled_count += 1
                                except Exception as e:
                                    print(f"  ⚠️  Select failed: {e}")
                                    stuck_fields.append({'field': question, 'error': str(e)})
                            
                            await asyncio.sleep(0.5)
                            continue
                        
                        # Handle regular inputs
                        answer = bot.get_answer(question, field['type'])
                        if not answer:
                            if field['required']:
                                stuck_fields.append({'field': question, 'error': 'Required but no answer'})
                            continue
                        
                        selector = None
                        if field['id']:
                            selector = f'#{field["id"]}'
                        elif field['name']:
                            selector = f'[name="{field["name"]}"]'
                        else:
                            selector = f'{field["tag"]}[placeholder="{field["placeholder"]}"]'
                        
                        if selector:
                            try:
                                element = page.locator(selector).first
                                await element.click()
                                await asyncio.sleep(0.3)
                                await element.fill(answer)
                                await asyncio.sleep(0.5)
                                
                                new_value = await element.input_value()
                                if new_value == answer:
                                    filled_count += 1
                                else:
                                    stuck_fields.append({'field': question, 'error': 'Verification failed'})
                            except Exception as e:
                                print(f"  ⚠️  Fill error: {str(e)[:50]}")
                                stuck_fields.append({'field': question, 'error': str(e)[:50]})
                        
                    except Exception as e:
                        print(f"  ⚠️  Field error: {str(e)[:50]}")
                        stuck_fields.append({'field': question, 'error': str(e)[:50]})
                        continue
                
                result['fields_filled'] = filled_count
                print(f"\n  📊 Filled: {filled_count}/{len(fields)}")
                
                # Check for validation errors
                validation_errors = await check_form_validation(page)
                
                if validation_errors:
                    print(f"\n  ⚠️  Validation Errors Found:")
                    for err in validation_errors[:5]:
                        print(f"     - {err}")
                
                # Handle stuck fields
                if stuck_fields or validation_errors:
                    print(f"\n  ⚠️  {len(stuck_fields)} fields couldn't be filled")
                    for sf in stuck_fields[:3]:
                        print(f"     - {sf['field']}: {sf['error']}")
                    
                    print("\n  🤔 Form not complete. Options:")
                    print("     1. Skip this job")
                    print("     2. Fill manually and submit")
                    print("     3. Try auto-submit anyway")
                    
                    choice = input("  Choose (1/2/3): ").strip()
                    
                    if choice == '1':
                        print("  ⏭️  Skipping...")
                        result['status'] = 'Incomplete (Skipped)'
                        output_data.append(result)
                        continue
                    elif choice == '2':
                        print("\n  ⏸️  Fill remaining fields manually...")
                        input("  Press ENTER when form is filled and ready to submit...")
                        result['status'] = 'Manual Fill'
                        result['submitted'] = 'Manual'
                        output_data.append(result)
                        continue
                
                # Try to submit
                print("\n  📤 Looking for submit button...")
                
                clicked = await page.evaluate('''() => {
                    const buttons = document.querySelectorAll('button, input[type="submit"], a');
                    
                    for (const btn of buttons) {
                        const text = btn.innerText || btn.value || '';
                        const textLower = text.toLowerCase();
                        
                        if ((textLower.includes('submit') || 
                             textLower.includes('apply') || 
                             textLower.includes('send application') ||
                             textLower.includes('send')) &&
                            btn.offsetParent !== null &&
                            !btn.disabled) {
                            btn.click();
                            return {success: true, text: text};
                        }
                    }
                    return {success: false};
                }''')
                
                if clicked['success']:
                    print(f"  ✅ Clicked: {clicked['text']}")
                    result['submitted'] = 'Yes'
                    await asyncio.sleep(4)
                    
                    # Check for success or errors
                    page_text = await page.inner_text('body')
                    page_lower = page_text.lower()
                    
                    # Check for validation errors after submit
                    post_submit_errors = await check_form_validation(page)
                    
                    if post_submit_errors:
                        print(f"\n  ❌ Submit failed - validation errors:")
                        for err in post_submit_errors[:3]:
                            print(f"     - {err}")
                        
                        result['status'] = 'Submit Failed (Validation)'
                        result['submitted'] = 'Failed'
                        
                        print("\n  🤔 Options:")
                        print("     1. Skip")
                        print("     2. Fix manually")
                        
                        choice = input("  Choose (1/2): ").strip()
                        if choice == '2':
                            input("  ⏸️  Fix errors and submit manually, then press ENTER...")
                            result['status'] = 'Manual Fix & Submit'
                    else:
                        # Check for success
                        success_words = ['thank', 'success', 'received', 'submitted', 'application sent']
                        if any(word in page_lower for word in success_words):
                            print("  🎉 APPLICATION SUCCESS!")
                            result['status'] = 'Success'
                        else:
                            print("  ⚠️  Submitted but no confirmation")
                            result['status'] = 'Submitted (Unconfirmed)'
                else:
                    print("  ⚠️  No submit button found")
                    result['status'] = 'Filled (No Submit Button)'
                    result['submitted'] = 'No'
                    
                    print("\n  🤔 Options:")
                    print("     1. Skip")
                    print("     2. Submit manually")
                    
                    choice = input("  Choose (1/2): ").strip()
                    if choice == '2':
                        input("  ⏸️  Submit manually and press ENTER...")
                        result['status'] = 'Manual Submit'
                        result['submitted'] = 'Manual'
                
            except Exception as e:
                error_msg = str(e)[:200]
                print(f"\n  ❌ ERROR: {error_msg}")
                result['status'] = 'Error'
                result['error'] = error_msg
            
            output_data.append(result)
            
            # Save after each job
            with open(output_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=['name', 'url', 'status', 'fields_found', 'fields_filled', 'submitted', 'error', 'timestamp'])
                writer.writeheader()
                writer.writerows(output_data)
            
            await asyncio.sleep(2)
        
        await browser.close()
    
    # Final summary
    print(f"\n{'='*80}")
    print("📊 FINAL SUMMARY")
    print(f"{'='*80}")
    
    success = sum(1 for r in output_data if 'Success' in r['status'])
    submitted = sum(1 for r in output_data if r['submitted'] == 'Yes')
    manual = sum(1 for r in output_data if r['submitted'] == 'Manual')
    skipped = sum(1 for r in output_data if 'Skip' in r['status'] or 'Login' in r['status'])
    errors = sum(1 for r in output_data if r['status'] == 'Error')
    
    print(f"Total: {len(output_data)}")
    print(f"✅ Success: {success}")
    print(f"📤 Auto-Submitted: {submitted}")
    print(f"✋ Manual: {manual}")
    print(f"⏭️  Skipped: {skipped}")
    print(f"❌ Errors: {errors}")
    print(f"💾 Memory: {len(bot.qa_memory)}")
    print(f"\n📁 Results: {output_file}")
    print(f"{'='*80}")

if __name__ == "__main__":
    asyncio.run(main())