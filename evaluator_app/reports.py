import io
import datetime
from django.utils import timezone
from docx import Document
from docx.shared import Inches, Pt
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, KeepTogether, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

def generate_student_excel_report(student, attendance_records, eval_stats, evaluations, tasks, batch_comparison=None):
    wb = Workbook()
    
    # 1. Summary Sheet
    ws_summary = wb.active
    ws_summary.title = "Student Summary"
    
    header_font = Font(bold=True, size=14)
    label_font = Font(bold=True)
    
    ws_summary['A1'] = f"Performance Report: {student.name}"
    ws_summary['A1'].font = header_font
    
    ws_summary['A3'] = "Batch:"
    ws_summary['B3'] = student.batch.name
    ws_summary['A4'] = "Roll Number:"
    ws_summary['B4'] = student.roll_number
    ws_summary['A5'] = "Overall Score:"
    ws_summary['B5'] = f"{student.average_score}%"
    
    ws_summary['A7'] = "Attendance Report"
    ws_summary['A7'].font = header_font
    
    total_att = attendance_records.count()
    present_att = attendance_records.filter(status__in=['PRESENT', 'LATE']).count()
    pct = round((present_att / total_att * 100) if total_att else 0, 1)
    
    ws_summary['A9'] = "Total Days:"
    ws_summary['B9'] = total_att
    ws_summary['A10'] = "Days Present:"
    ws_summary['B10'] = present_att
    ws_summary['A11'] = "Attendance %:"
    ws_summary['B11'] = f"{pct}%"
    
    if batch_comparison:
        ws_summary['C11'] = f"(Batch Avg: {batch_comparison['avg_attendance']}%)"
    
    ws_summary['A13'] = "Task Report"
    ws_summary['A13'].font = header_font
    
    total_tasks = tasks.count()
    completed_tasks = tasks.filter(status='COMPLETED').count()
    task_pct = round((completed_tasks / total_tasks * 100) if total_tasks else 0, 1)
    
    ws_summary['A15'] = "Total Tasks Given:"
    ws_summary['B15'] = total_tasks
    ws_summary['A16'] = "Tasks Completed:"
    ws_summary['B16'] = completed_tasks
    ws_summary['A17'] = "Completion %:"
    ws_summary['B17'] = f"{task_pct}%"
    
    if batch_comparison:
        ws_summary['C17'] = f"(Batch Avg: {batch_comparison['avg_task_completion']}%)"
        
    ws_summary['A19'] = "Overall Progress / Performance Trend"
    ws_summary['A19'].font = header_font
    
    row = 21
    evals_asc = list(evaluations)[::-1]
    for idx, ev in enumerate(evals_asc):
        ws_summary[f'A{row}'] = f"Evaluation {idx+1} ({ev.date}):"
        ws_summary[f'B{row}'] = f"{ev.total_score}%"
        row += 1
        
    row += 2
    ws_summary[f'A{row}'] = "Recent Evaluator Remarks"
    ws_summary[f'A{row}'].font = header_font
    row += 2
    for ev in evaluations[:5]:
        ws_summary[f'A{row}'] = f"Date: {ev.date}"
        ws_summary[f'A{row}'].font = label_font
        ws_summary[f'B{row}'] = f"Score: {ev.total_score}% | Evaluator: {ev.evaluator.get_full_name() or ev.evaluator.username}"
        
        ws_summary[f'A{row+1}'] = "Strongest Areas:"
        ws_summary[f'B{row+1}'] = ev.strongest_areas
        ws_summary[f'A{row+2}'] = "Areas for Improvement:"
        ws_summary[f'B{row+2}'] = ev.areas_for_improvement
        ws_summary[f'A{row+3}'] = "General Remarks:"
        ws_summary[f'B{row+3}'] = ev.general_remarks
        row += 5
        
    for col in ws_summary.columns:
        ws_summary.column_dimensions[col[0].column_letter].width = 25

    # 2. Tasks Sheet
    ws_tasks = wb.create_sheet(title="Specific Task Details")
    task_headers = ["Task Title", "Day Given", "Date Given", "Due Date", "Status", "Completed At", "Evaluator Remarks"]
    ws_tasks.append(task_headers)
    
    for c in range(1, len(task_headers)+1):
        cell = ws_tasks.cell(row=1, column=c)
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="DDDDDD", end_color="DDDDDD", fill_type="solid")
        
    for task in tasks:
        ws_tasks.append([
            task.title,
            task.assigned_date.strftime('%A') if task.assigned_date else '',
            task.assigned_date.strftime('%Y-%m-%d') if task.assigned_date else '',
            task.due_date.strftime('%Y-%m-%d') if task.due_date else '',
            task.status,
            task.completed_at.strftime('%Y-%m-%d %H:%M') if task.completed_at else '',
            task.evaluator_remarks
        ])
        
    for col in ws_tasks.columns:
        ws_tasks.column_dimensions[col[0].column_letter].width = 20

    # 3. Attendance Sheet
    ws_att = wb.create_sheet(title="Attendance Dates")
    ws_att.append(["Date", "Status", "Marked By"])
    for c in range(1, 4):
        ws_att.cell(row=1, column=c).font = Font(bold=True)
    
    for att in attendance_records:
        marked_by = att.marked_by.get_full_name() or att.marked_by.username if att.marked_by else "System"
        ws_att.append([att.date.strftime('%Y-%m-%d'), att.status, marked_by])
        
    ws_att.column_dimensions['A'].width = 15
    ws_att.column_dimensions['B'].width = 15
    ws_att.column_dimensions['C'].width = 25

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output


def generate_student_docx_report(student, attendance_records, eval_stats, evaluations, tasks, batch_comparison=None):
    doc = Document()
    doc.add_heading(f"Performance Report: {student.name}", 0)
    
    doc.add_paragraph(f"Batch: {student.batch.name}")
    doc.add_paragraph(f"Roll Number: {student.roll_number}")
    doc.add_paragraph(f"Overall Score: {student.average_score}%")
    
    # Attendance
    doc.add_heading('Attendance Report', level=1)
    total_att = attendance_records.count()
    present_att = attendance_records.filter(status__in=['PRESENT', 'LATE']).count()
    pct = round((present_att / total_att * 100) if total_att else 0, 1)
    
    doc.add_paragraph(f"Total Days: {total_att}")
    doc.add_paragraph(f"Days Present: {present_att}")
    doc.add_paragraph(f"Attendance %: {pct}%")
    
    if batch_comparison:
        doc.add_paragraph(f"Batch Average Attendance: {batch_comparison['avg_attendance']}%")
    
    doc.add_heading('Detailed Attendance', level=2)
    table_att = doc.add_table(rows=1, cols=3)
    table_att.style = 'Table Grid'
    hdr_att = table_att.rows[0].cells
    hdr_att[0].text = 'Date'
    hdr_att[1].text = 'Status'
    hdr_att[2].text = 'Marked By'
    
    for att in attendance_records:
        row = table_att.add_row().cells
        marked_by = att.marked_by.get_full_name() or att.marked_by.username if att.marked_by else "System"
        row[0].text = att.date.strftime('%Y-%m-%d')
        row[1].text = att.status
        row[2].text = marked_by
    
    # Tasks Summary
    doc.add_heading('Task Report Summary', level=1)
    total_tasks = tasks.count()
    completed_tasks = tasks.filter(status='COMPLETED').count()
    task_pct = round((completed_tasks / total_tasks * 100) if total_tasks else 0, 1)
    
    doc.add_paragraph(f"Total Tasks Given: {total_tasks}")
    doc.add_paragraph(f"Tasks Completed: {completed_tasks}")
    doc.add_paragraph(f"Completion %: {task_pct}%")
    
    if batch_comparison:
        doc.add_paragraph(f"Batch Average Task Completion: {batch_comparison['avg_task_completion']}%")
    
    # Specific Tasks Table
    doc.add_heading('Specific Task Details', level=2)
    table = doc.add_table(rows=1, cols=5)
    table.style = 'Table Grid'
    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = 'Task'
    hdr_cells[1].text = 'Day'
    hdr_cells[2].text = 'Given Date'
    hdr_cells[3].text = 'Status'
    hdr_cells[4].text = 'Completed Date'
    
    for task in tasks:
        row_cells = table.add_row().cells
        row_cells[0].text = task.title
        row_cells[1].text = task.assigned_date.strftime('%A') if task.assigned_date else '-'
        row_cells[2].text = task.assigned_date.strftime('%Y-%m-%d') if task.assigned_date else '-'
        row_cells[3].text = task.status
        row_cells[4].text = task.completed_at.strftime('%Y-%m-%d') if task.completed_at else '-'
        
    # Performance Trend
    doc.add_heading('Overall Progress / Performance Trend', level=1)
    evals_asc = list(evaluations)[::-1]
    for idx, ev in enumerate(evals_asc):
        doc.add_paragraph(f"Evaluation {idx+1} ({ev.date}) → {ev.total_score}%")
        
    # Evaluations
    doc.add_heading('Evaluator Insights', level=1)
    for ev in evaluations[:3]:
        p = doc.add_paragraph()
        p.add_run(f"Date: {ev.date} | Score: {ev.total_score}%\n").bold = True
        if ev.strongest_areas:
            p.add_run("Strongest Areas: ").bold = True
            p.add_run(f"{ev.strongest_areas}\n")
        if ev.areas_for_improvement:
            p.add_run("Areas for Improvement: ").bold = True
            p.add_run(f"{ev.areas_for_improvement}\n")
        if ev.general_remarks:
            p.add_run("Remarks: ").bold = True
            p.add_run(f"{ev.general_remarks}\n")
            
    output = io.BytesIO()
    doc.save(output)
    output.seek(0)
    return output


def generate_student_pdf_report(student, attendance_records, eval_stats, evaluations, tasks, batch_comparison=None):
    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []
    
    # Title
    elements.append(Paragraph(f"Performance Report: {student.name}", styles['Title']))
    elements.append(Paragraph(f"Batch: {student.batch.name} | Roll Number: {student.roll_number} | Overall Score: {student.average_score}%", styles['Normal']))
    elements.append(Spacer(1, 12))
    
    # Attendance
    elements.append(Paragraph("Attendance Report", styles['Heading2']))
    total_att = attendance_records.count()
    present_att = attendance_records.filter(status__in=['PRESENT', 'LATE']).count()
    pct = round((present_att / total_att * 100) if total_att else 0, 1)
    
    batch_att_str = f" ({batch_comparison['avg_attendance']}% Batch Avg)" if batch_comparison else ""
    
    att_data = [
        ["Total Days", "Days Present", "Attendance %"],
        [str(total_att), str(present_att), f"{pct}%{batch_att_str}"]
    ]
    t_att = Table(att_data, colWidths=[100, 100, 150])
    t_att.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.grey),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,0), 12),
        ('GRID', (0,0), (-1,-1), 1, colors.black)
    ]))
    elements.append(t_att)
    elements.append(Spacer(1, 12))
    
    elements.append(Paragraph("Detailed Attendance", styles['Heading2']))
    att_detail_data = [["Date", "Status", "Marked By"]]
    for att in attendance_records:
        marked_by = att.marked_by.get_full_name() or att.marked_by.username if att.marked_by else "System"
        att_detail_data.append([att.date.strftime('%Y-%m-%d'), att.status, marked_by])
        
    t_att_detail = Table(att_detail_data, colWidths=[100, 100, 150])
    t_att_detail.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('TEXTCOLOR', (0,0), (-1,0), colors.black),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,0), 8),
        ('GRID', (0,0), (-1,-1), 1, colors.black),
    ]))
    elements.append(t_att_detail)
    elements.append(Spacer(1, 24))
    
    # Tasks Summary
    elements.append(Paragraph("Task Report Summary", styles['Heading2']))
    total_tasks = tasks.count()
    completed_tasks = tasks.filter(status='COMPLETED').count()
    task_pct = round((completed_tasks / total_tasks * 100) if total_tasks else 0, 1)
    
    batch_task_str = f" ({batch_comparison['avg_task_completion']}% Batch Avg)" if batch_comparison else ""
    
    task_data = [
        ["Total Tasks Given", "Tasks Completed", "Completion %"],
        [str(total_tasks), str(completed_tasks), f"{task_pct}%{batch_task_str}"]
    ]
    t_task = Table(task_data, colWidths=[120, 120, 150])
    t_task.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.grey),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,0), 12),
        ('GRID', (0,0), (-1,-1), 1, colors.black)
    ]))
    elements.append(t_task)
    elements.append(Spacer(1, 24))
    
    # Task Details Table
    elements.append(Paragraph("Specific Task Details", styles['Heading2']))
    task_table_data = [["Task Title", "Day", "Given Date", "Status", "Completed Date"]]
    for task in tasks:
        task_table_data.append([
            Paragraph(task.title, styles['Normal']),
            task.assigned_date.strftime('%A') if task.assigned_date else '-',
            task.assigned_date.strftime('%Y-%m-%d') if task.assigned_date else '-',
            task.status,
            task.completed_at.strftime('%Y-%m-%d') if task.completed_at else '-'
        ])
        
    t_task_details = Table(task_table_data, colWidths=[150, 70, 70, 70, 90])
    t_task_details.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('TEXTCOLOR', (0,0), (-1,0), colors.black),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,0), 8),
        ('GRID', (0,0), (-1,-1), 1, colors.black),
        ('VALIGN',(0,0),(-1,-1),'TOP'),
    ]))
    elements.append(t_task_details)
    elements.append(Spacer(1, 24))
    
    # Performance Trend
    elements.append(Paragraph("Overall Progress / Performance Trend", styles['Heading2']))
    evals_asc = list(evaluations)[::-1]
    for idx, ev in enumerate(evals_asc):
        elements.append(Paragraph(f"<b>Evaluation {idx+1} ({ev.date}) &rarr; {ev.total_score}%</b>", styles['Normal']))
    elements.append(Spacer(1, 16))
    
    # Evaluator Remarks
    elements.append(Paragraph("Evaluator Insights & Remarks", styles['Heading2']))
    for ev in evaluations[:3]:
        elements.append(Paragraph(f"<b>Date: {ev.date} (Score: {ev.total_score}%)</b>", styles['Normal']))
        if ev.strongest_areas:
            elements.append(Paragraph(f"<b>Strongest Areas:</b> {ev.strongest_areas}", styles['Normal']))
        if ev.areas_for_improvement:
            elements.append(Paragraph(f"<b>Improvement Needed:</b> {ev.areas_for_improvement}", styles['Normal']))
        if ev.general_remarks:
            elements.append(Paragraph(f"<b>Remarks:</b> {ev.general_remarks}", styles['Normal']))
        elements.append(Spacer(1, 10))
        
    doc.build(elements)
    output.seek(0)
    return output


class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas to dynamically compute total page count
    and render professional headers and footers with page numbering.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_header_and_footer(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_header_and_footer(self, page_count):
        self.saveState()
        self.setFont('Helvetica', 8)
        self.setFillColor(colors.HexColor('#64748B'))
        
        # Bottom footer line and text
        self.setStrokeColor(colors.HexColor('#CBD5E1'))
        self.setLineWidth(0.5)
        self.line(36, 30, A4[0] - 36, 30)
        
        self.drawString(36, 18, 'CogniLearn Evaluator • Confidential & Official Attendance Statement')
        self.drawRightString(A4[0] - 36, 18, f'Page {self._pageNumber} of {page_count}')
        
        # Running top header for pages 2 and later
        if self._pageNumber > 1:
            self.drawString(36, A4[1] - 22, 'CogniLearn Evaluator — Student Attendance Log (Continued)')
            self.drawRightString(A4[0] - 36, A4[1] - 22, datetime.datetime.now().strftime('%d-%b-%Y'))
            self.line(36, A4[1] - 26, A4[0] - 36, A4[1] - 26)
            
        self.restoreState()


def generate_student_attendance_pdf(student, attendance_items, month_label=None, stats=None):
    """
    Generates a high-quality, professional executive attendance statement in PDF format
    using ReportLab. Formatted with student profile, attendance KPI metrics, and a
    structured table including Date, Day, Month, Status, and Remarks.
    """
    output = io.BytesIO()
    # Filter out any cancelled records completely
    attendance_items = [it for it in attendance_items if it.get('status', '').upper() != 'CANCELLED']
    doc = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=42
    )
    styles = getSampleStyleSheet()
    
    # Custom styles
    brand_sub_style = ParagraphStyle(
        'BrandSub',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#4F46E5')
    )
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=colors.HexColor('#0F172A')
    )
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor('#475569')
    )
    meta_box_style = ParagraphStyle(
        'MetaBoxText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor('#1E293B')
    )
    meta_box_bold = ParagraphStyle(
        'MetaBoxBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor('#0F172A')
    )
    kpi_num_style = ParagraphStyle(
        'KPINum',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=16,
        alignment=1,
        textColor=colors.HexColor('#0F172A')
    )
    kpi_lbl_style = ParagraphStyle(
        'KPILbl',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.5,
        leading=9.5,
        alignment=1,
        textColor=colors.HexColor('#64748B')
    )
    section_h_style = ParagraphStyle(
        'SectionH',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=15,
        textColor=colors.HexColor('#1E293B')
    )
    cell_style = ParagraphStyle(
        'CellRegular',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#1E293B')
    )
    cell_bold = ParagraphStyle(
        'CellBoldText',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#0F172A')
    )
    remarks_cell_style = ParagraphStyle(
        'RemarksCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor('#475569')
    )

    elements = []
    
    # 1. Header Banner
    generated_now = timezone.now().strftime('%d %B %Y, %I:%M %p')
    header_data = [
        [
            Paragraph("<b>COGNILearn ACADEMIC PORTAL</b>", brand_sub_style),
            Paragraph(f"<font color='#64748B'>Generated:</font> <b>{generated_now}</b>", ParagraphStyle('DateH', parent=styles['Normal'], fontName='Helvetica', fontSize=8, alignment=2, textColor=colors.HexColor('#475569')))
        ],
        [
            Paragraph("STUDENT ATTENDANCE STATEMENT", title_style),
            Paragraph(f"<font color='#64748B'>Center:</font> <b>{student.batch.location.name if student.batch and student.batch.location else 'Main Center'}</b>", ParagraphStyle('CenterH', parent=styles['Normal'], fontName='Helvetica', fontSize=8.5, alignment=2, textColor=colors.HexColor('#1E293B')))
        ],
        [
            Paragraph(f"Official session-by-session attendance & participation record", subtitle_style),
            ""
        ]
    ]
    header_table = Table(header_data, colWidths=[330, 193])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 1),
        ('TOPPADDING', (0,0), (-1,-1), 0),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 4))
    elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#4F46E5'), spaceBefore=2, spaceAfter=10))

    # 2. Student & Batch Details Card
    period_str = month_label if month_label else "Full Program Attendance (All Dates)"
    student_details_data = [
        [
            Paragraph(f"<b>Student Name:</b> {student.name}", meta_box_style),
            Paragraph(f"<b>Roll Number:</b> <code>{student.roll_number}</code>", meta_box_style),
            Paragraph(f"<b>Batch:</b> {student.batch.name if student.batch else '-'}", meta_box_style),
        ],
        [
            Paragraph(f"<b>Class Days:</b> {student.batch.class_days if student.batch else '-'}", meta_box_style),
            Paragraph(f"<b>Location / Center:</b> {student.batch.location.name if student.batch and student.batch.location else '-'}", meta_box_style),
            Paragraph(f"<b>Period Covered:</b> {period_str}", meta_box_style),
        ]
    ]
    student_box = Table(student_details_data, colWidths=[174, 174, 175])
    student_box.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F8FAFC')),
        ('BOX', (0,0), (-1,-1), 0.75, colors.HexColor('#E2E8F0')),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#F1F5F9')),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    elements.append(student_box)
    elements.append(Spacer(1, 10))

    # 3. Attendance Summary KPI Cards Strip
    if stats:
        pct = stats.get('percentage', 0.0)
        pct_color = '#15803D' if pct >= 75 else ('#B45309' if pct >= 60 else '#B91C1C')
        kpi_data = [
            [
                Paragraph(f"<b>{stats.get('total', len(attendance_items))}</b>", kpi_num_style),
                Paragraph(f"<b><font color='#15803D'>{stats.get('present', 0)}</font></b>", kpi_num_style),
                Paragraph(f"<b><font color='#B91C1C'>{stats.get('absent', 0)}</font></b>", kpi_num_style),
                Paragraph(f"<b><font color='#B45309'>{stats.get('late', 0) + stats.get('excused', 0)}</font></b>", kpi_num_style),
                Paragraph(f"<b><font color='{pct_color}'>{pct}%</font></b>", kpi_num_style),
            ],
            [
                Paragraph("TOTAL SESSIONS", kpi_lbl_style),
                Paragraph("PRESENT", kpi_lbl_style),
                Paragraph("ABSENT", kpi_lbl_style),
                Paragraph("LATE / EXCUSED", kpi_lbl_style),
                Paragraph("ATTENDANCE RATE", kpi_lbl_style),
            ]
        ]
        kpi_table = Table(kpi_data, colWidths=[104, 104, 105, 105, 105])
        kpi_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.white),
            ('BOX', (0,0), (-1,-1), 0.75, colors.HexColor('#CBD5E1')),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
            ('TOPPADDING', (0,0), (-1,0), 7),
            ('BOTTOMPADDING', (0,0), (-1,0), 2),
            ('TOPPADDING', (0,1), (-1,1), 1),
            ('BOTTOMPADDING', (0,1), (-1,1), 7),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ]))
        elements.append(kpi_table)
        elements.append(Spacer(1, 14))

    # 4. Detailed Attendance History Table
    elements.append(Paragraph("<b>Detailed Session Attendance Log</b>", section_h_style))
    elements.append(Spacer(1, 6))

    # Table Header
    table_rows = [
        ['#', 'Date', 'Day', 'Month', 'Status']
    ]

    for idx, item in enumerate(attendance_items, start=1):
        d = item['date']
        # Format date as DD/MM/YYYY
        date_formatted = d.strftime('%d/%m/%Y')
        day_str = d.strftime('%A')
        month_str = d.strftime('%B %Y')
        status_str = item.get('status', 'ABSENT').upper()
        if 'PRESENT' in status_str:
            status_str = 'PRESENT'
        elif 'ABSENT' in status_str or 'NOT MARKED' in status_str:
            status_str = 'ABSENT'
        elif 'LATE' in status_str:
            status_str = 'LATE'
        elif 'EXCUSED' in status_str:
            status_str = 'EXCUSED'
        
        table_rows.append([
            str(idx),
            date_formatted,
            day_str,
            month_str,
            status_str
        ])

    col_widths = [35, 115, 120, 125, 128]
    att_table = Table(table_rows, colWidths=col_widths, repeatRows=1)
    
    table_styles = [
        # Table Header Styling
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1E293B')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 9),
        ('ALIGN', (0,0), (-1,0), 'LEFT'),
        ('ALIGN', (0,0), (0,-1), 'CENTER'),   # Sl No centered
        ('ALIGN', (4,0), (4,-1), 'CENTER'),   # Status centered
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
        ('TOPPADDING', (0,0), (-1,0), 6),
        ('BOTTOMPADDING', (0,0), (-1,0), 6),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,1), (-1,-1), 6),
        ('BOTTOMPADDING', (0,1), (-1,-1), 6),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
        ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
        ('FONTSIZE', (0,1), (-1,-1), 8.5),
    ]

    # Row-specific styling for Status badges & alternating zebra stripes
    for row_idx, item in enumerate(attendance_items, start=1):
        st = item.get('status', '').upper()
        
        # Alternating row background for columns 0 to 3
        if row_idx % 2 == 0:
            table_styles.append(('BACKGROUND', (0, row_idx), (3, row_idx), colors.HexColor('#F8FAFC')))
        else:
            table_styles.append(('BACKGROUND', (0, row_idx), (3, row_idx), colors.white))

        # Status badge background & text colors
        if 'PRESENT' in st:
            bg_col = colors.HexColor('#DCFCE7')  # Light green
            tx_col = colors.HexColor('#15803D')  # Dark green
        elif 'LATE' in st:
            bg_col = colors.HexColor('#FEF3C7')  # Light amber
            tx_col = colors.HexColor('#B45309')  # Dark amber
        elif 'CANCELLED' in st:
            bg_col = colors.HexColor('#F1F5F9')  # Light slate
            tx_col = colors.HexColor('#475569')  # Dark slate
        elif 'EXCUSED' in st:
            bg_col = colors.HexColor('#DBEAFE')  # Light blue
            tx_col = colors.HexColor('#1D4ED8')  # Dark blue
        else: # ABSENT or Not Marked
            bg_col = colors.HexColor('#FEE2E2')  # Light red
            tx_col = colors.HexColor('#B91C1C')  # Dark red

        table_styles.append(('BACKGROUND', (4, row_idx), (4, row_idx), bg_col))
        table_styles.append(('TEXTCOLOR', (4, row_idx), (4, row_idx), tx_col))
        table_styles.append(('FONTNAME', (4, row_idx), (4, row_idx), 'Helvetica-Bold'))
        table_styles.append(('FONTSIZE', (4, row_idx), (4, row_idx), 8))

    att_table.setStyle(TableStyle(table_styles))
    elements.append(att_table)
    elements.append(Spacer(1, 16))

    # 5. Signatures & Official Validation Block
    sign_data = [
        [
            Paragraph("<b>Verified By (Evaluator / Faculty):</b>", meta_box_bold),
            Paragraph("<b>Academic Head / Center Coordinator:</b>", meta_box_bold)
        ],
        [
            Spacer(1, 24),
            Spacer(1, 24)
        ],
        [
            Paragraph("___________________________________<br/><font color='#64748B' size=7.5>Signature & Date</font>", meta_box_style),
            Paragraph("___________________________________<br/><font color='#64748B' size=7.5>Seal & Signature</font>", meta_box_style)
        ],
        [
            Paragraph("<font color='#94A3B8' size=7><i>* Document generated by CogniLearn Evaluator. Valid for academic records and performance review.</i></font>", meta_box_style),
            ""
        ]
    ]
    sign_table = Table(sign_data, colWidths=[261, 262])
    sign_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ('TOPPADDING', (0,0), (-1,-1), 2),
    ]))
    
    elements.append(KeepTogether([sign_table]))

    doc.build(elements, canvasmaker=NumberedCanvas)
    output.seek(0)
    return output


class CollegeLetterheadCanvas(canvas.Canvas):
    """
    Canvas for official College Attendance Report letterhead.
    Renders official teal footer at the bottom margin of each page.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_letterhead_footer()
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_letterhead_footer(self):
        self.saveState()
        teal = colors.HexColor('#00838F')
        self.setFont('Helvetica-Bold', 10)
        self.setFillColor(teal)
        self.drawString(54, 76, 'JHF IT Innovations Private Limited')
        self.setFont('Helvetica', 7.5)
        self.drawString(54, 64, 'CIN: U58200KL2024PTC091151')
        self.drawString(54, 53, 'Registered Address: 5th Floor, Asiatic Business Centre, Kazhakuttam, Trivandrum – 695582')
        self.drawString(54, 42, 'PH: +91- 8891559888; E-mail: info@cognilearn.org ; Website : www.cognilearn.com')
        self.drawString(54, 31, 'Branches: Trivandrum | Calicut')
        self.restoreState()


def generate_college_attendance_pdf(student, attendance_items, college_name=None, month_label=None):
    """
    Generates an official College Attendance Report on JHF IT Innovations Private Limited
    letterhead, formatted specifically for college submission & internship verification.
    """
    import os
    from django.conf import settings

    # Filter out any cancelled records completely
    attendance_items = [it for it in attendance_items if it.get('status', '').upper() != 'CANCELLED']

    output = io.BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=54,
        rightMargin=54,
        topMargin=44,
        bottomMargin=95
    )
    styles = getSampleStyleSheet()

    # Typography styles matching the official college format
    title_style = ParagraphStyle(
        'CollegeDocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=13.5,
        leading=17,
        alignment=1, # Center
        spaceAfter=14,
        textColor=colors.black
    )
    body_style = ParagraphStyle(
        'CollegeDocBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=15,
        textColor=colors.black
    )
    body_bold = ParagraphStyle(
        'CollegeDocBodyBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=15,
        textColor=colors.black
    )

    elements = []

    # 1. Logos Header Table (JHF on left, CogniLearn on right)
    base_dir = getattr(settings, 'BASE_DIR', '')
    img_dir = os.path.join(base_dir, 'evaluator_app', 'static', 'images')
    jhf_logo_path = os.path.join(img_dir, 'jhf_logo.png')
    cog_logo_path = os.path.join(img_dir, 'cognilearn_logo.png')
    seal_path = os.path.join(img_dir, 'jhf_seal_signature.png')

    logo_cells = []
    if os.path.exists(jhf_logo_path):
        logo_cells.append(RLImage(jhf_logo_path, width=120, height=50))
    else:
        logo_cells.append(Paragraph("<b>JHF IT</b><br/><font size=7 color='#00A3C4'>INNOVATIONS PVT LTD</font>", body_bold))

    if os.path.exists(cog_logo_path):
        logo_cells.append(RLImage(cog_logo_path, width=76, height=58))
    else:
        logo_cells.append(Paragraph("<b>CogniLearn</b>", body_bold))

    logo_table = Table([[logo_cells[0], logo_cells[1]]], colWidths=[280, 207])
    logo_table.setStyle(TableStyle([
        ('ALIGN', (0,0), (0,0), 'LEFT'),
        ('ALIGN', (1,0), (1,0), 'RIGHT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
    ]))
    elements.append(logo_table)
    elements.append(Spacer(1, 28))

    # 2. Heading
    elements.append(Paragraph("<b>ATTENDANCE REPORT</b>", title_style))
    elements.append(Spacer(1, 16))

    # 3. Recipient Section
    college = college_name or "AWH Engineering College, Calicut"
    elements.append(Paragraph(f"To<br/><b>{college}</b>", body_style))
    elements.append(Spacer(1, 14))

    # 4. Salutation
    elements.append(Paragraph("Dear Sir/Madam,", body_style))
    elements.append(Spacer(1, 10))

    # 5. Introductory Paragraph
    # Determine Class / Year string dynamically
    class_parts = []
    if student.batch:
        class_parts.append(student.batch.name)
    if student.student_class:
        class_parts.append(student.student_class)
    elif student.academic_year:
        class_parts.append(student.academic_year)
    else:
        class_parts.append("Second Year (S3)")
    class_str = ", ".join(class_parts)

    location_name = student.batch.location.name if student.batch and student.batch.location else "Calicut"

    intro_text = (
        f"This is to inform you that <b>Ms./Mr. {student.name}</b>, a student of <b>{class_str}</b>, "
        f"from your institution visited our {location_name} Corporate Office in connection with "
        f"her/his internship under the <b>CogniLearn Experienceship Program</b>."
    )
    elements.append(Paragraph(intro_text, body_style))
    elements.append(Spacer(1, 18))

    # 6. Attendance Table (3 columns: Date, Day, Activity / Status)
    table_rows = [
        ['Date', 'Day', 'Activity / Status']
    ]

    for item in attendance_items:
        d = item['date']
        date_str = d.strftime('%d-%m-%Y')
        day_str = d.strftime('%A')
        st_raw = item.get('status', 'PRESENT').upper()
        
        # Display status in Title Case as shown in college letter: Present, Absent
        if 'PRESENT' in st_raw:
            display_status = 'Present'
        elif 'ABSENT' in st_raw or 'NOT MARKED' in st_raw:
            display_status = 'Absent'
        elif 'LATE' in st_raw:
            display_status = 'Late'
        elif 'EXCUSED' in st_raw:
            display_status = 'Excused'
        else:
            display_status = item.get('status', 'Present').title()

        table_rows.append([
            date_str,
            day_str,
            display_status
        ])

    table_widths = [110, 170, 207]
    table = Table(table_rows, colWidths=table_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 9.5),
        ('ALIGN', (0,0), (0,-1), 'CENTER'), # Date centered
        ('ALIGN', (1,0), (1,-1), 'LEFT'),   # Day left
        ('ALIGN', (2,0), (2,-1), 'LEFT'),   # Activity/Status left
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 18))

    # 7. Closing Text
    elements.append(Paragraph("For any further information or clarification, please feel free to contact us.", body_style))
    elements.append(Spacer(1, 14))
    elements.append(Paragraph("Yours sincerely,<br/><br/>For JHF IT Innovations Private Limited", body_style))
    elements.append(Spacer(1, 10))

    # 8. Signature and Seal
    if os.path.exists(seal_path):
        sig_img = RLImage(seal_path, width=170, height=85)
        sig_table = Table([[sig_img]], colWidths=[487])
        sig_table.setStyle(TableStyle([
            ('LEFTPADDING', (0,0), (-1,-1), 0),
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
            ('TOPPADDING', (0,0), (-1,-1), 0),
        ]))
        elements.append(sig_table)
    
    elements.append(Spacer(1, 4))
    elements.append(Paragraph("<b>Arif Muhammed TA</b><br/>CEO", body_style))

    doc.build(elements, canvasmaker=CollegeLetterheadCanvas)
    output.seek(0)
    return output

