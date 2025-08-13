import time
from django.core.management.base import BaseCommand
from django.db import transaction
from app.models import ScrapeJob
from app.utils_selenium import scrape_predictz_selenium

class Command(BaseCommand):
    help = 'Process pending scrape jobs from the database.'

    def handle(self, *args, **options):
        self.stdout.write("Starting background worker...")
        while True:
            job_to_process = None
            try:
                with transaction.atomic():
                    # Find a pending job and lock it to prevent other workers from picking it up
                    job_to_process = ScrapeJob.objects.select_for_update(skip_locked=True).filter(status='PENDING').order_by('created_at').first()
                    if job_to_process:
                        job_to_process.status = 'PROCESSING'
                        job_to_process.save()
                        self.stdout.write(self.style.SUCCESS(f"Processing job {job_to_process.id} with payload {job_to_process.payload}"))

                if job_to_process:
                    try:
                        # Execute the actual task
                        date_arg = job_to_process.payload.get('date')
                        result = scrape_predictz_selenium(date_arg=date_arg, stdout=self.stdout)

                        # Update job with result
                        job_to_process.status = 'COMPLETED'
                        job_to_process.result = result
                        job_to_process.save()
                        self.stdout.write(self.style.SUCCESS(f"Job {job_to_process.id} completed successfully."))

                    except Exception as e:
                        self.stderr.write(self.style.ERROR(f"Error processing job {job_to_process.id}: {e}"))
                        job_to_process.status = 'FAILED'
                        job_to_process.result = {'error': str(e)}
                        job_to_process.save()
                else:
                    self.stdout.write("No pending jobs found. Waiting...")
                    time.sleep(15) # Wait for 15 seconds before checking again

            except Exception as e:
                self.stderr.write(self.style.ERROR(f"An unexpected error occurred in the worker loop: {e}"))
                # If the error was during DB transaction, the job might not be locked
                # or might be rolled back. Sleeping to avoid a fast error loop.
                time.sleep(30)