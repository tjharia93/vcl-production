def on_submit(doc, method):
    doc.update_job_card_progress()


def on_cancel(doc, method):
    doc.update_job_card_progress()
