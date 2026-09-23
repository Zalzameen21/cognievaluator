// ==============================================================================
// STUDENT EVALUATOR - MAIN JAVASCRIPT
// ==============================================================================

document.addEventListener('DOMContentLoaded', () => {
    // 1. Theme Toggle
    initTheme();

    // 2. Schedule Type toggle in batch forms
    initScheduleToggle();

    // 3. Universal Modal System (Open, Close, Cancel, Backdrop & Esc)
    initGenericModals();

    // 4. Daily Evaluation Modal & Live Score Calculator
    initEvaluationModal();

    // 5. Attendance Quick Mark Helpers
    initAttendanceControls();
});

// -----------------------------------------------------------------------------
// UNIVERSAL MODAL SYSTEM (OPEN, CLOSE, CANCEL, BACKDROP, ESCAPE)
// -----------------------------------------------------------------------------
function initGenericModals() {
    // 1. Open Modals via [data-modal="modalId"]
    document.addEventListener('click', (e) => {
        const openTrigger = e.target.closest('[data-modal]');
        if (openTrigger) {
            e.preventDefault();
            const modalId = openTrigger.getAttribute('data-modal');
            const targetModal = document.getElementById(modalId);
            if (targetModal) {
                targetModal.classList.add('active');
                document.body.style.overflow = 'hidden';
            }
            return;
        }

        // 2. Close Modals via [data-close-modal], [data-modal-close], .modal-close
        const closeTrigger = e.target.closest('[data-close-modal], [data-modal-close], .modal-close');
        if (closeTrigger) {
            e.preventDefault();
            const specificModalId = closeTrigger.getAttribute('data-close-modal');
            let modalToClose = null;
            if (specificModalId) {
                modalToClose = document.getElementById(specificModalId);
            }
            if (!modalToClose) {
                modalToClose = closeTrigger.closest('.modal-backdrop');
            }
            if (modalToClose) {
                modalToClose.classList.remove('active');
                if (!document.querySelector('.modal-backdrop.active')) {
                    document.body.style.overflow = '';
                }
            }
            return;
        }

        // 3. Click directly on semi-transparent backdrop outside .modal-content
        if (e.target.classList.contains('modal-backdrop') && e.target.classList.contains('active')) {
            e.target.classList.remove('active');
            if (!document.querySelector('.modal-backdrop.active')) {
                document.body.style.overflow = '';
            }
        }
    });

    // 4. Close active modal with Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' || e.key === 'Esc') {
            const activeModals = document.querySelectorAll('.modal-backdrop.active');
            if (activeModals.length > 0) {
                activeModals.forEach(m => m.classList.remove('active'));
                document.body.style.overflow = '';
            }
        }
    });
}

// -----------------------------------------------------------------------------
// THEME MANAGEMENT
// -----------------------------------------------------------------------------
function initTheme() {
    const savedTheme = localStorage.getItem('eva_theme') || 'light';
    document.documentElement.setAttribute('data-theme', savedTheme);
    updateThemeIcon(savedTheme);

    const toggleBtn = document.getElementById('themeToggleBtn');
    if (toggleBtn) {
        toggleBtn.addEventListener('click', () => {
            const current = document.documentElement.getAttribute('data-theme') || 'light';
            const next = current === 'dark' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', next);
            localStorage.setItem('eva_theme', next);
            updateThemeIcon(next);
        });
    }
}

function updateThemeIcon(theme) {
    const btn = document.getElementById('themeToggleBtn');
    if (!btn) return;
    btn.innerHTML = theme === 'dark' 
        ? '<i class="bi bi-sun-fill"></i>' 
        : '<i class="bi bi-moon-stars-fill"></i>';
}

// -----------------------------------------------------------------------------
// BATCH SCHEDULE FORM TOGGLE
// -----------------------------------------------------------------------------
function initScheduleToggle() {
    const scheduleSelect = document.getElementById('id_schedule_type');
    const classDayGroup = document.getElementById('classDayFormGroup');

    if (scheduleSelect && classDayGroup) {
        const checkVisibility = () => {
            if (scheduleSelect.value === 'WEEKLY') {
                classDayGroup.style.display = 'block';
            } else {
                classDayGroup.style.display = 'none';
            }
        };
        scheduleSelect.addEventListener('change', checkVisibility);
        checkVisibility(); // Initial run
    }
}

// -----------------------------------------------------------------------------
// DAILY EVALUATION MODAL & LIVE SCORE CALCULATOR
// -----------------------------------------------------------------------------
function initEvaluationModal() {
    const modal = document.getElementById('evaluationModal');
    if (!modal) return;

    const closeBtns = modal.querySelectorAll('.modal-close, [data-modal-close]');
    closeBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            modal.classList.remove('active');
        });
    });

    // Score inputs
    const inputs = {
        punct: document.getElementById('modal_punct_score'),
        tutor_int: document.getElementById('modal_tutor_int_score'),
        peer_int: document.getElementById('modal_peer_int_score'),
        study_ten: document.getElementById('modal_study_ten_score'),
        tasks_given: document.getElementById('modal_tasks_given'),
        tasks_completed: document.getElementById('modal_tasks_completed'),
        pres: document.getElementById('modal_pres_score'),
        prob: document.getElementById('modal_prob_score'),
        ppt: document.getElementById('modal_ppt_score'),
        comm: document.getElementById('modal_comm_score'),
        sugg: document.getElementById('modal_sugg_score'),
        doubt: document.getElementById('modal_doubt_score'),
    };

    const labels = {
        punct: document.getElementById('val_punct'),
        tutor_int: document.getElementById('val_tutor_int'),
        peer_int: document.getElementById('val_peer_int'),
        study_ten: document.getElementById('val_study_ten'),
        pres: document.getElementById('val_pres'),
        prob: document.getElementById('val_prob'),
        ppt: document.getElementById('val_ppt'),
        comm: document.getElementById('val_comm'),
        sugg: document.getElementById('val_sugg'),
        doubt: document.getElementById('val_doubt'),
    };

    const liveTotalEl = document.getElementById('liveTotalScore');
    const liveGradeEl = document.getElementById('liveGradeBadge');
    const taskRateBadge = document.getElementById('liveTaskRateBadge');

    function calculateLiveScore() {
        const punct = parseFloat(inputs.punct?.value || 80);
        const tutor_int = parseFloat(inputs.tutor_int?.value || 80);
        const peer_int = parseFloat(inputs.peer_int?.value || 80);
        const study_ten = parseFloat(inputs.study_ten?.value || 80);
        
        const tasks_given = Math.max(1, parseInt(inputs.tasks_given?.value || 5));
        const tasks_completed = Math.max(0, parseInt(inputs.tasks_completed?.value || 5));
        const task_pct = Math.min(100, Math.round((tasks_completed / tasks_given) * 100));

        const pres = parseFloat(inputs.pres?.value || 75);
        const prob = parseFloat(inputs.prob?.value || 75);
        const ppt = parseFloat(inputs.ppt?.value || 75);

        const comm = parseFloat(inputs.comm?.value || 75);
        const sugg = parseFloat(inputs.sugg?.value || 80);
        const doubt = parseFloat(inputs.doubt?.value || 75);

        // Update labels
        if (labels.punct) labels.punct.textContent = punct;
        if (labels.tutor_int) labels.tutor_int.textContent = tutor_int;
        if (labels.peer_int) labels.peer_int.textContent = peer_int;
        if (labels.study_ten) labels.study_ten.textContent = study_ten;
        if (labels.pres) labels.pres.textContent = pres;
        if (labels.prob) labels.prob.textContent = prob;
        if (labels.ppt) labels.ppt.textContent = ppt;
        if (labels.comm) labels.comm.textContent = comm;
        if (labels.sugg) labels.sugg.textContent = sugg;
        if (labels.doubt) labels.doubt.textContent = doubt;

        if (taskRateBadge) {
            taskRateBadge.textContent = `${task_pct}%`;
            taskRateBadge.className = `badge-grade ${task_pct >= 80 ? 'grade-aplus' : (task_pct >= 60 ? 'grade-b' : 'grade-ni')}`;
        }

        // Composite Weighted Total Calculation
        const total = (
            (punct * 0.08) +
            (tutor_int * 0.08) +
            (peer_int * 0.08) +
            (study_ten * 0.10) +
            (task_pct * 0.12) +
            (pres * 0.12) +
            (prob * 0.16) +
            (ppt * 0.10) +
            (comm * 0.06) +
            (sugg * 0.05) +
            (doubt * 0.05)
        ).toFixed(1);

        if (liveTotalEl) liveTotalEl.textContent = `${total}%`;

        let gradeClass = 'grade-ni';
        let gradeText = 'Needs Improvement (< 50)';

        if (total >= 90) {
            gradeClass = 'grade-aplus';
            gradeText = 'A+ (Outstanding)';
        } else if (total >= 80) {
            gradeClass = 'grade-a';
            gradeText = 'A (Excellent)';
        } else if (total >= 70) {
            gradeClass = 'grade-bplus';
            gradeText = 'B+ (Very Good)';
        } else if (total >= 60) {
            gradeClass = 'grade-b';
            gradeText = 'B (Good)';
        } else if (total >= 50) {
            gradeClass = 'grade-c';
            gradeText = 'C (Average)';
        }

        if (liveGradeEl) {
            liveGradeEl.className = `badge-grade ${gradeClass}`;
            liveGradeEl.textContent = gradeText;
        }
    }

    Object.values(inputs).forEach(input => {
        if (input) {
            input.addEventListener('input', calculateLiveScore);
        }
    });

    // Handle open evaluation modal buttons
    const evaluateBtns = document.querySelectorAll('.btn-open-evaluate');
    evaluateBtns.forEach(btn => {
        btn.addEventListener('click', async () => {
            const studentId = btn.getAttribute('data-student-id');
            const evalDate = btn.getAttribute('data-date');
            
            try {
                const res = await fetch(`/evaluations/student/${studentId}/?date=${evalDate}&format=json`, {
                    headers: { 'X-Requested-With': 'XMLHttpRequest' }
                });
                const data = await res.json();

                // Populate modal headers & attendance
                document.getElementById('modal_student_name').textContent = data.student_name;
                document.getElementById('modal_student_roll').textContent = data.roll_number;
                document.getElementById('modal_student_batch').textContent = data.batch_name;
                document.getElementById('modal_student_att').textContent = `${data.attendance_percentage}%`;
                document.getElementById('modal_eval_date').textContent = data.date;
                document.getElementById('modal_topic').value = data.topic || 'Daily Practical & Concept Evaluation';

                // Populate Behavioral
                inputs.punct.value = data.punctuality_score ?? 80;
                inputs.tutor_int.value = data.tutor_interaction_score ?? 80;
                inputs.peer_int.value = data.classmate_interaction_score ?? 80;
                inputs.study_ten.value = data.tendency_to_study_score ?? 80;
                
                // Tasks
                inputs.tasks_given.value = data.tasks_given ?? 5;
                inputs.tasks_completed.value = data.tasks_completed ?? 5;

                // Project & Presentation
                inputs.pres.value = data.presentation_score ?? 75;
                inputs.prob.value = data.problem_solving_score ?? 75;
                inputs.ppt.value = data.ppt_evaluation_score ?? 75;
                document.getElementById('modal_ppt_slides').value = data.ppt_slide_count ?? 6;
                document.getElementById('modal_ppt_images').checked = data.ppt_has_images !== false;
                document.getElementById('modal_ppt_notes').value = data.ppt_explanation_notes || '';

                // Communication
                inputs.comm.value = data.communication_score ?? 75;
                inputs.sugg.value = data.suggestion_implementation_score ?? 80;
                inputs.doubt.value = data.doubt_clearing_score ?? 75;

                // Remarks
                document.getElementById('modal_strongest').value = data.strongest_areas || '';
                document.getElementById('modal_improvements').value = data.areas_for_improvement || '';
                document.getElementById('modal_interested').value = data.interested_areas || '';
                document.getElementById('modal_general_remarks').value = data.general_remarks || '';

                // Reset new task input fields
                const newTaskTitle = document.getElementById('modal_new_task_title');
                if (newTaskTitle) newTaskTitle.value = '';
                const newTaskDue = document.getElementById('modal_new_task_due');
                if (newTaskDue) newTaskDue.value = '';
                const newTaskDesc = document.getElementById('modal_new_task_desc');
                if (newTaskDesc) newTaskDesc.value = '';

                // Render Student Tasks list
                const tasksContainer = document.getElementById('modal_tasks_container');
                if (tasksContainer) {
                    if (data.tasks && data.tasks.length > 0) {
                        let html = '<div style="display:flex; flex-direction:column; gap:8px;">';
                        data.tasks.forEach(t => {
                            let statusBadge = '';
                            if (t.status === 'COMPLETED') {
                                statusBadge = '<span class="badge" style="background:rgba(16,185,129,0.15);color:#10B981;font-size:10px;font-weight:700;"><i class="bi bi-check-circle-fill"></i> Completed</span>';
                            } else if (t.status === 'LATE') {
                                statusBadge = '<span class="badge" style="background:rgba(139,92,246,0.15);color:#8B5CF6;font-size:10px;font-weight:700;"><i class="bi bi-alarm-fill"></i> Completed Late</span>';
                            } else if (t.computed_status === 'OVERDUE') {
                                statusBadge = '<span class="badge" style="background:rgba(239,68,68,0.15);color:#EF4444;font-size:10px;font-weight:700;"><i class="bi bi-exclamation-triangle-fill"></i> Overdue</span>';
                            } else {
                                statusBadge = '<span class="badge" style="background:rgba(245,158,11,0.15);color:#F59E0B;font-size:10px;font-weight:700;"><i class="bi bi-hourglass-split"></i> Pending</span>';
                            }

                            html += `
                                <div style="background:var(--bg-surface); padding:10px 14px; border-radius:var(--radius-sm); border:1px solid var(--border-color); display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
                                    <div>
                                        <div style="font-weight:700; font-size:12px; color:var(--text-main);">${t.title}</div>
                                        <div style="font-size:11px; color:var(--text-muted); display:flex; gap:12px; margin-top:2px;">
                                            <span><strong>Given:</strong> ${t.assigned_date_display}</span>
                                            ${t.due_date ? `<span><strong>Due:</strong> ${t.due_date_display}</span>` : ''}
                                            <span><strong>Completed:</strong> <span style="color:var(--primary);">${t.completed_at_display}</span></span>
                                        </div>
                                    </div>
                                    <div style="display:flex; align-items:center; gap:8px;">
                                        ${statusBadge}
                                        ${t.status === 'PENDING' ? `
                                            <button type="button" class="btn btn-secondary btn-sm btn-quick-complete-task" data-task-id="${t.id}" style="font-size:10px; padding:2px 8px;">
                                                <i class="bi bi-check2"></i> Mark Done
                                            </button>
                                        ` : ''}
                                    </div>
                                </div>
                            `;
                        });
                        html += '</div>';
                        tasksContainer.innerHTML = html;

                        // Attach Quick Complete click handler
                        tasksContainer.querySelectorAll('.btn-quick-complete-task').forEach(cBtn => {
                            cBtn.addEventListener('click', async (e) => {
                                e.stopPropagation();
                                const taskId = cBtn.getAttribute('data-task-id');
                                const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
                                try {
                                    const cRes = await fetch(`/tasks/${taskId}/update-status/`, {
                                        method: 'POST',
                                        headers: {
                                            'Content-Type': 'application/x-www-form-urlencoded',
                                            'X-Requested-With': 'XMLHttpRequest',
                                            'X-CSRFToken': csrfToken
                                        },
                                        body: new URLSearchParams({
                                            'status': 'COMPLETED'
                                        })
                                    });
                                    const cData = await cRes.json();
                                    if (cData.success) {
                                        cBtn.parentElement.innerHTML = '<span class="badge" style="background:rgba(16,185,129,0.15);color:#10B981;font-size:10px;font-weight:700;"><i class="bi bi-check-circle-fill"></i> Completed</span>';
                                    }
                                } catch(e) {
                                    console.error("Error quick completing task", e);
                                }
                            });
                        });
                    } else {
                        tasksContainer.innerHTML = '<div style="font-size:12px; color:var(--text-dim); font-style:italic;">No active specific tasks assigned. You can assign one below.</div>';
                    }
                }

                const form = document.getElementById('modalEvaluationForm');
                form.action = `/evaluations/student/${studentId}/?date=${evalDate}`;

                calculateLiveScore();
                modal.classList.add('active');
            } catch (err) {
                console.error("Failed to load student evaluation details:", err);
            }
        });
    });
}


// -----------------------------------------------------------------------------
// ATTENDANCE CONTROLS & BULK SWITCHERS
// -----------------------------------------------------------------------------
function initAttendanceControls() {
    // 1. Bulk Mark All Present
    const markAllPresentBtn = document.getElementById('markAllPresentBtn');
    if (markAllPresentBtn) {
        markAllPresentBtn.addEventListener('click', () => {
            document.querySelectorAll('.att-student-row').forEach(row => {
                const presentInput = row.querySelector('input[value="PRESENT"]');
                if (presentInput) {
                    presentInput.checked = true;
                    highlightSelectedAtt(row, 'PRESENT');
                }
            });
            recalculateAttendanceStats();
        });
    }

    // 2. Bulk Mark All Absent
    const markAllAbsentBtn = document.getElementById('markAllAbsentBtn');
    if (markAllAbsentBtn) {
        markAllAbsentBtn.addEventListener('click', () => {
            document.querySelectorAll('.att-student-row').forEach(row => {
                const absentInput = row.querySelector('input[value="ABSENT"]');
                if (absentInput) {
                    absentInput.checked = true;
                    highlightSelectedAtt(row, 'ABSENT');
                }
            });
            recalculateAttendanceStats();
        });
    }

    // 3. Individual Radio click highlights
    document.querySelectorAll('.att-radio-btn').forEach(label => {
        label.addEventListener('click', (e) => {
            const row = label.closest('.att-student-row');
            const radio = label.querySelector('input[type="radio"]');
            if (radio && row) {
                radio.checked = true;
                highlightSelectedAtt(row, radio.value);
                recalculateAttendanceStats();
            }
        });
    });
}

function highlightSelectedAtt(row, status) {
    row.querySelectorAll('.att-radio-btn').forEach(btn => {
        btn.classList.remove('active', 'present', 'late', 'absent', 'excused');
        const input = btn.querySelector('input[type="radio"]');
        if (input && input.value === status) {
            btn.classList.add('active', status.toLowerCase());
        }
    });
}

function recalculateAttendanceStats() {
    const rows = document.querySelectorAll('.att-student-row');
    let present = 0, late = 0, absent = 0, excused = 0;
    
    rows.forEach(row => {
        const checked = row.querySelector('input[type="radio"]:checked');
        if (checked) {
            if (checked.value === 'PRESENT') present++;
            else if (checked.value === 'LATE') late++;
            else if (checked.value === 'ABSENT') absent++;
            else if (checked.value === 'EXCUSED') excused++;
        }
    });

    const total = rows.length;
    const rate = total > 0 ? (((present + late) / total) * 100).toFixed(1) : 0;

    const pEl = document.getElementById('livePresentCount');
    const aEl = document.getElementById('liveAbsentCount');
    const lEl = document.getElementById('liveLateCount');
    const eEl = document.getElementById('liveExcusedCount');
    const rEl = document.getElementById('liveAttendanceRate');

    if (pEl) pEl.textContent = present;
    if (aEl) aEl.textContent = absent;
    if (lEl) lEl.textContent = late;
    if (eEl) eEl.textContent = excused;
    if (rEl) rEl.textContent = `${rate}%`;
}
