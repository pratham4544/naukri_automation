#!/usr/bin/env python3
"""
Job Application Email Sender
Automatically generates tailored resumes and cover letters, then sends them to HR emails.
"""

import pandas as pd
import os
import sys
import smtplib
import subprocess
import glob
import time
import logging
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Optional, Tuple
from dotenv import load_dotenv

# LangChain imports
from langchain_groq import ChatGroq
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.prompts import PromptTemplate

# =============================================================================
# CONFIGURATION
# =============================================================================

class Config:
    """Configuration settings for the application"""
    
    # Email settings
    SENDER_EMAIL = "prathameshshete609@gmail.com"
    APP_PASSWORD = "xhrkzetnnyjmblzj"
    SMTP_SERVER = "smtp.gmail.com"
    SMTP_PORT = 587
    
    # File paths
    CSV_FILE = "output_with_emails_2.csv"
    RESUME_PDF = "ignored/Prathamesh_Resume.pdf"
    OUTPUT_CSV = "sent_emails_status.csv"
    
    # LLM settings
    LLM_MODEL = "llama-3.1-8b-instant"
    LLM_TEMPERATURE = 0
    MAX_RETRIES = 3
    
    # Rate limiting (safer approach with delays)
    DELAY_BETWEEN_EMAILS = 2  # seconds between each email
    BATCH_SIZE = 10  # emails per batch
    BATCH_DELAY = 60  # seconds between batches
    
    # LLM Usage (set at runtime)
    USE_LLM = False  # Will be set by user choice
    
    # Directories
    TEMP_DIR = "temp_resumes"


# =============================================================================
# LOGGING SETUP
# =============================================================================

def setup_logging():
    """Configure logging to both file and console"""
    
    # Create logs directory
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # Create log filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"email_sender_{timestamp}.log"
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    return logging.getLogger(__name__)


# =============================================================================
# DEFAULT COVER LETTER (FALLBACK)
# =============================================================================

DEFAULT_COVER_LETTER = """Dear Hiring Manager,

I am writing to express my interest in the AI Engineer position at your organization. I am an AI/ML Engineer with over 2.5 years of hands-on experience in designing, developing, and deploying production-grade AI systems, with a strong focus on Generative AI and transformer-based models.

My professional experience includes working extensively with Large Language Models (LLMs), Retrieval-Augmented Generation (RAG) pipelines, model fine-tuning, and semantic search systems. I have built scalable AI solutions using Python, Hugging Face, LangChain, FastAPI, and TensorFlow, and have experience deploying and maintaining these systems on cloud platforms such as AWS.

I have worked on real-world AI applications including conversational AI systems, AI-driven interview platforms, document-based chatbots, and data-driven automation solutions. I am comfortable collaborating with cross-functional teams and building reliable, production-ready solutions that align with business objectives.

I am highly motivated, quick to learn, and passionate about applying AI technologies to solve complex problems and deliver measurable impact. I believe my technical background, problem-solving mindset, and practical experience would allow me to contribute effectively to your team.

Please find my resume attached for your review. I would welcome the opportunity to further discuss how my skills and experience align with your requirements.

Thank you for your time and consideration.

Kind regards,  
Prathamesh Shete  
AI / ML Engineer  
Email: prathameshshete609@gmail.com  
Phone: +91 9970939341  
Portfolio: prathameshshete.in"""


# =============================================================================
# RESUME TEMPLATES
# =============================================================================

RESUME_TEMPLATE = """
Create a professional resume in Markdown (.md) format.

Use my existing resume content as the base and rewrite, reorganize, and enhance the skills, experience, and summary so they align closely with the job description provided.

Rules:
- Keep all information truthful and derived from my original resume
- Optimize wording and skills to match the job description
- Use clear Markdown headings and bullet points
- Keep the resume concise and ATS-friendly
- Do not invent experience or credentials

Job Description:
{job_description}

Current Resume Text:
{resume_text}

Output: A complete, well-structured resume in valid Markdown (.md) format. No explanations, only the Markdown content.
"""

COVER_LETTER_TEMPLATE = """
Given the following resume and job description, generate a tailored cover letter that highlights relevant skills and experiences from the resume to match the job requirements.

Make it professional, concise, and engaging. Include:
1. A strong opening that mentions the specific position
2. 2-3 paragraphs highlighting relevant experience and skills
3. A closing paragraph expressing enthusiasm and call to action

Resume: {resume_text}
Job Description: {job_description}

Cover Letter:
"""


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def check_dependencies(logger):
    """Check if all required dependencies are installed"""
    
    logger.info("🔍 Checking dependencies...")
    
    # Check pandoc
    try:
        subprocess.run(["pandoc", "--version"], 
                      capture_output=True, 
                      text=True, 
                      check=True)
        logger.info("✅ Pandoc found")
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.error("❌ Pandoc not found. Install with: sudo apt-get install pandoc texlive-xetex")
        sys.exit(1)
    
    logger.info("✅ All dependencies satisfied")


def validate_environment(logger):
    """Validate environment variables and files"""
    
    logger.info("🔍 Validating environment...")
    
    # Load environment variables
    load_dotenv()
    
    # Check GROQ API key
    groq_key = os.getenv('GROQ_API_KEY')
    if not groq_key:
        logger.error("❌ GROQ_API_KEY not found in environment")
        logger.error("Create a .env file with: GROQ_API_KEY=your_key_here")
        sys.exit(1)
    
    logger.info("✅ GROQ API key found")
    
    # Check CSV file
    if not Path(Config.CSV_FILE).exists():
        logger.error(f"❌ CSV file not found: {Config.CSV_FILE}")
        sys.exit(1)
    
    logger.info(f"✅ CSV file found: {Config.CSV_FILE}")
    
    # Check resume PDF
    if not Path(Config.RESUME_PDF).exists():
        logger.error(f"❌ Resume PDF not found: {Config.RESUME_PDF}")
        sys.exit(1)
    
    logger.info(f"✅ Resume PDF found: {Config.RESUME_PDF}")
    
    return groq_key


def create_temp_directory(logger):
    """Create temporary directory for generated files"""
    
    temp_dir = Path(Config.TEMP_DIR)
    temp_dir.mkdir(exist_ok=True)
    logger.info(f"✅ Temporary directory: {temp_dir}")
    
    return temp_dir


# =============================================================================
# LLM FUNCTIONS
# =============================================================================

def initialize_llm(api_key: str, logger) -> ChatGroq:
    """Initialize the LLM"""
    
    logger.info("🤖 Initializing LLM...")
    
    try:
        llm = ChatGroq(
            model=Config.LLM_MODEL,
            temperature=Config.LLM_TEMPERATURE,
            max_tokens=None,
            timeout=None,
            max_retries=Config.MAX_RETRIES,
            api_key=api_key
        )
        
        # Test the LLM
        response = llm.invoke("Hi")
        logger.info("✅ LLM initialized successfully")
        
        return llm
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize LLM: {str(e)}")
        sys.exit(1)


def load_resume(file_path: str, logger) -> str:
    """Load and parse resume PDF"""
    
    logger.info(f"📄 Loading resume from: {file_path}")
    
    try:
        loader = PyPDFLoader(file_path)
        docs = loader.load()
        
        resume_text = " ".join([doc.page_content for doc in docs])
        
        logger.info(f"✅ Resume loaded ({len(resume_text)} characters)")
        
        return resume_text
        
    except Exception as e:
        logger.error(f"❌ Failed to load resume: {str(e)}")
        sys.exit(1)


def md_to_pdf(md_file: str, pdf_file: str, logger) -> bool:
    """Convert Markdown to PDF using pandoc"""
    
    try:
        subprocess.run([
            "pandoc",
            md_file,
            "-o",
            pdf_file,
            "--pdf-engine=xelatex"
        ], check=True, capture_output=True, text=True)
        
        return True
        
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Pandoc conversion failed: {e.stderr}")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error in MD to PDF conversion: {str(e)}")
        return False


def generate_cover_letter(job_description: str, resume_text: str, llm, logger) -> Optional[str]:
    """Generate a tailored cover letter"""
    
    try:
        prompt = PromptTemplate(
            template=COVER_LETTER_TEMPLATE,
            input_variables=["resume_text", "job_description"]
        )
        
        chain = prompt | llm
        result = chain.invoke({
            "resume_text": resume_text,
            "job_description": job_description
        })
        
        return result.content
        
    except Exception as e:
        logger.error(f"❌ Failed to generate cover letter: {str(e)}")
        return None


def generate_tailored_resume(job_description: str, resume_text: str, llm, temp_dir: Path, 
                            index: int, logger) -> Optional[str]:
    """Generate a tailored resume PDF"""
    
    try:
        # Generate resume markdown
        prompt = PromptTemplate(
            template=RESUME_TEMPLATE,
            input_variables=["resume_text", "job_description"]
        )
        
        chain = prompt | llm
        result = chain.invoke({
            "resume_text": resume_text,
            "job_description": job_description
        })
        
        # Save markdown file
        md_file = temp_dir / f"resume_{index}.md"
        pdf_file = temp_dir / f"resume_{index}.pdf"
        
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(result.content)
        
        # Convert to PDF
        if md_to_pdf(str(md_file), str(pdf_file), logger):
            return str(pdf_file)
        else:
            return None
        
    except Exception as e:
        logger.error(f"❌ Failed to generate resume: {str(e)}")
        return None


# =============================================================================
# EMAIL FUNCTIONS
# =============================================================================

def send_email_with_retry(receiver_email: str, subject: str, cover_letter: str,
                          resume_pdf_path: str, logger, max_attempts: int = 3) -> Tuple[bool, str]:
    """Send email with retry logic"""
    
    for attempt in range(1, max_attempts + 1):
        try:
            # Validate inputs
            if not os.path.exists(resume_pdf_path):
                return False, f"Resume file not found: {resume_pdf_path}"
            
            if not receiver_email or '@' not in receiver_email:
                return False, f"Invalid email address: {receiver_email}"
            
            # Create email message
            msg = EmailMessage()
            msg["From"] = Config.SENDER_EMAIL
            msg["To"] = receiver_email
            msg["Subject"] = subject
            msg.set_content(cover_letter)
            
            # Attach resume PDF
            with open(resume_pdf_path, "rb") as f:
                file_data = f.read()
                file_name = os.path.basename(resume_pdf_path)
            
            msg.add_attachment(
                file_data,
                maintype="application",
                subtype="pdf",
                filename=file_name
            )
            
            # Send email
            with smtplib.SMTP(Config.SMTP_SERVER, Config.SMTP_PORT, timeout=30) as server:
                server.starttls()
                server.login(Config.SENDER_EMAIL, Config.APP_PASSWORD)
                server.send_message(msg)
            
            logger.info(f"✅ Email sent to {receiver_email}")
            return True, "Sent successfully"
            
        except smtplib.SMTPAuthenticationError:
            return False, "SMTP authentication failed - check email/password"
            
        except smtplib.SMTPException as e:
            logger.warning(f"⚠️  Attempt {attempt}/{max_attempts} failed for {receiver_email}: {str(e)}")
            if attempt < max_attempts:
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                return False, f"SMTP error after {max_attempts} attempts: {str(e)}"
        
        except Exception as e:
            logger.warning(f"⚠️  Attempt {attempt}/{max_attempts} failed for {receiver_email}: {str(e)}")
            if attempt < max_attempts:
                time.sleep(2 ** attempt)
            else:
                return False, f"Unexpected error after {max_attempts} attempts: {str(e)}"
    
    return False, "Max retries exceeded"


# =============================================================================
# DATA PROCESSING
# =============================================================================

def load_and_filter_data(csv_file: str, logger) -> pd.DataFrame:
    """Load CSV and filter for valid email addresses"""
    
    logger.info(f"📊 Loading data from: {csv_file}")
    
    try:
        df = pd.read_csv(csv_file)
        logger.info(f"✅ Loaded {len(df)} total records")
        
        # Filter for valid emails
        df_filtered = df[df['career_email'].notna() & (df['career_email'] != '')]
        logger.info(f"✅ Found {len(df_filtered)} records with emails")
        
        # Remove duplicates by email
        df_unique = df_filtered.drop_duplicates(subset=['career_email'], keep='first')
        
        if len(df_filtered) != len(df_unique):
            logger.info(f"ℹ️  Removed {len(df_filtered) - len(df_unique)} duplicate emails")
        
        logger.info(f"✅ Final dataset: {len(df_unique)} unique job applications")
        
        return df_unique.reset_index(drop=True)
        
    except Exception as e:
        logger.error(f"❌ Failed to load/filter data: {str(e)}")
        sys.exit(1)


# =============================================================================
# MAIN EXECUTION
# =============================================================================

def main():
    """Main execution function"""
    
    # Setup
    logger = setup_logging()
    logger.info("=" * 80)
    logger.info("🚀 JOB APPLICATION EMAIL SENDER STARTED")
    logger.info("=" * 80)
    
    start_time = time.time()
    
    # Validate environment
    check_dependencies(logger)
    groq_key = validate_environment(logger)
    temp_dir = create_temp_directory(logger)
    
    # Initialize LLM
    llm = initialize_llm(groq_key, logger)
    
    # Load resume
    resume_text = load_resume(Config.RESUME_PDF, logger)
    
    # Load and filter data
    df = load_and_filter_data(Config.CSV_FILE, logger)
    
    if len(df) == 0:
        logger.error("❌ No valid records to process")
        sys.exit(1)
    
    # Ask user: Use LLM or Default content?
    logger.info("\n" + "=" * 80)
    logger.info("🤖 CONTENT GENERATION MODE")
    logger.info("=" * 80)
    print("\nChoose your email content mode:")
    print("1. 🤖 Use LLM (AI-generated tailored resumes & cover letters)")
    print("   - Slower but customized for each job")
    print("   - Falls back to defaults if AI fails")
    print("   - Requires GROQ API calls")
    print("\n2. 📋 Use Defaults (same resume & cover letter for all)")
    print("   - Much faster (no AI generation)")
    print("   - Same content for every job")
    print("   - No API costs")
    
    mode_choice = input("\nEnter your choice (1 or 2): ").strip()
    
    if mode_choice == '2':
        Config.USE_LLM = False
        logger.info("✅ Selected: DEFAULT mode - Using same resume & cover letter for all jobs")
        logger.info("⚡ This will be much faster!")
    else:
        Config.USE_LLM = True
        logger.info("✅ Selected: LLM mode - AI will generate tailored content for each job")
        logger.info("⏳ This will take longer but emails will be customized")
    
    # Confirm before proceeding
    logger.info("\n" + "=" * 80)
    logger.info(f"📧 Ready to send {len(df)} job application emails")
    logger.info(f"📝 Mode: {'LLM (Tailored)' if Config.USE_LLM else 'DEFAULT (Same for all)'}")
    logger.info("=" * 80)
    
    response = input("\n⚠️  Do you want to proceed? (yes/no): ").strip().lower()
    if response not in ['yes', 'y']:
        logger.info("❌ Aborted by user")
        sys.exit(0)
    
    # Process applications
    results = []
    successful = 0
    failed = 0
    
    logger.info("\n" + "=" * 80)
    logger.info("📨 PROCESSING JOB APPLICATIONS")
    logger.info("=" * 80)
    
    for idx, row in df.iterrows():
        logger.info(f"\n--- Processing {idx + 1}/{len(df)} ---")
        logger.info(f"Company: {row['company']}")
        logger.info(f"Position: {row['title']}")
        logger.info(f"Email: {row['career_email']}")
        
        result = {
            'company': row['company'],
            'title': row['title'],
            'email': row['career_email'],
            'status': 'pending',
            'message': '',
            'timestamp': datetime.now().isoformat(),
            'used_defaults': False
        }
        
        try:
            cover_letter = None
            resume_pdf_path = None
            used_defaults = False
            
            # Check if user wants to use LLM
            if Config.USE_LLM:
                # Try to generate tailored cover letter
                logger.info("📝 Generating tailored cover letter...")
                cover_letter = generate_cover_letter(row['job_description'], resume_text, llm, logger)
                
                # Try to generate tailored resume
                if cover_letter:
                    logger.info("📄 Generating tailored resume...")
                    resume_pdf_path = generate_tailored_resume(
                        row['job_description'], 
                        resume_text, 
                        llm, 
                        temp_dir, 
                        idx, 
                        logger
                    )
                
                # FALLBACK: If AI generation failed, use defaults
                if not cover_letter or not resume_pdf_path:
                    logger.warning(f"⚠️  AI generation failed - using DEFAULT resume & cover letter")
                    cover_letter = DEFAULT_COVER_LETTER
                    resume_pdf_path = Config.RESUME_PDF
                    used_defaults = True
                    result['used_defaults'] = True
            else:
                # User chose to skip LLM - use defaults directly
                logger.info(f"📋 Using DEFAULT resume & cover letter (LLM disabled)")
                cover_letter = DEFAULT_COVER_LETTER
                resume_pdf_path = Config.RESUME_PDF
                used_defaults = True
                result['used_defaults'] = True
            
            # Send email (with tailored or default content)
            logger.info(f"📧 Sending email{'(with defaults)' if used_defaults else ''}...")
            
            # Handle multiple emails (take first one)
            email_address = row['career_email'].split(',')[0].strip()
            subject = f"Application for {row['title']} at {row['company']}"
            
            success, message = send_email_with_retry(
                email_address,
                subject,
                cover_letter,
                resume_pdf_path,
                logger
            )
            
            # Update result
            if success:
                result['status'] = 'sent'
                result['message'] = f"Sent successfully{' (with defaults)' if used_defaults else ''}"
                logger.info(f"✅ Successfully sent{' (with defaults)' if used_defaults else ''}!")
                successful += 1
            else:
                result['status'] = 'failed'
                result['message'] = f"Email sending failed: {message}"
                logger.error(f"❌ {message}")
                logger.warning(f"⚠️  Skipping and continuing to next job")
                failed += 1
            
            results.append(result)
            
            # Rate limiting - add delays between emails
            if (idx + 1) % Config.BATCH_SIZE == 0:
                logger.info(f"⏸️  Batch complete. Waiting {Config.BATCH_DELAY}s before next batch...")
                time.sleep(Config.BATCH_DELAY)
            else:
                time.sleep(Config.DELAY_BETWEEN_EMAILS)
        
        except Exception as e:
            logger.error(f"❌ Unexpected error: {str(e)}")
            
            # LAST RESORT: Try with defaults even after exception
            try:
                logger.warning(f"⚠️  Attempting final send with defaults after exception...")
                email_address = row['career_email'].split(',')[0].strip()
                subject = f"Application for {row['title']} at {row['company']}"
                
                success, message = send_email_with_retry(
                    email_address,
                    subject,
                    DEFAULT_COVER_LETTER,
                    Config.RESUME_PDF,
                    logger
                )
                
                if success:
                    result['status'] = 'sent'
                    result['message'] = 'Sent with defaults after error recovery'
                    result['used_defaults'] = True
                    logger.info(f"✅ Recovered and sent with defaults!")
                    results.append(result)
                    successful += 1
                    continue
                    
            except Exception as recovery_error:
                logger.error(f"❌ Recovery also failed: {str(recovery_error)}")
            
            result['status'] = 'failed'
            result['message'] = f'Unexpected error: {str(e)}'
            results.append(result)
            failed += 1
            logger.warning(f"⚠️  Skipping and continuing to next job")
    
    # Save results to CSV
    logger.info("\n" + "=" * 80)
    logger.info("💾 SAVING RESULTS")
    logger.info("=" * 80)
    
    results_df = pd.DataFrame(results)
    results_df.to_csv(Config.OUTPUT_CSV, index=False)
    logger.info(f"✅ Results saved to: {Config.OUTPUT_CSV}")
    
    # Cleanup temporary files
    logger.info("\n🧹 Cleaning up temporary files...")
    
    try:
        file_patterns = [f"{Config.TEMP_DIR}/*.pdf", f"{Config.TEMP_DIR}/*.md"]
        deleted_count = 0
        
        for pattern in file_patterns:
            files = glob.glob(pattern)
            for file in files:
                try:
                    os.remove(file)
                    deleted_count += 1
                except Exception as e:
                    logger.warning(f"⚠️  Could not delete {file}: {str(e)}")
        
        logger.info(f"✅ Deleted {deleted_count} temporary files")
        
    except Exception as e:
        logger.warning(f"⚠️  Cleanup error: {str(e)}")
    
    # Final summary report
    elapsed_time = time.time() - start_time
    
    # Calculate statistics
    sent_with_defaults = sum(1 for r in results if r.get('used_defaults', False) and r['status'] == 'sent')
    sent_tailored = successful - sent_with_defaults
    
    logger.info("\n" + "=" * 80)
    logger.info("📊 FINAL SUMMARY")
    logger.info("=" * 80)
    logger.info(f"📝 Mode used: {'LLM (Tailored)' if Config.USE_LLM else 'DEFAULT (Same for all)'}")
    logger.info(f"✅ Successful: {successful}")
    logger.info(f"   📝 Sent with tailored content: {sent_tailored}")
    logger.info(f"   📋 Sent with default content: {sent_with_defaults}")
    logger.info(f"❌ Failed: {failed}")
    logger.info(f"📧 Total processed: {len(results)}")
    logger.info(f"⏱️  Time elapsed: {elapsed_time:.2f} seconds")
    logger.info(f"📄 Results saved to: {Config.OUTPUT_CSV}")
    logger.info("=" * 80)
    
    if failed > 0:
        logger.warning(f"\n⚠️  {failed} applications failed. Check {Config.OUTPUT_CSV} for details.")
    
    logger.info("\n✅ Process completed!")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Process interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Fatal error: {str(e)}")
        sys.exit(1)