const $ = (selector) => document.querySelector(selector);
const state = { counselors: [], selectedSlot: null };

function todayInSeoul() {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit'
  }).formatToParts(new Date());
  const value = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return value.year + '-' + value.month + '-' + value.day;
}

function formatDate(value) {
  const date = new Date(value + 'T00:00:00+09:00');
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul', month: 'long', day: 'numeric', weekday: 'short'
  }).format(date);
}

function formatTime(value) {
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit', hour12: false
  }).format(new Date(value));
}

function showMessage(target, text, kind) {
  target.hidden = !text;
  target.className = 'message ' + (kind || 'info');
  target.textContent = text;
}

async function api(path, options) {
  const config = Object.assign({
    cache: 'no-store',
    headers: { 'Content-Type': 'application/json' }
  }, options || {});
  const response = await fetch(path, config);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || '요청을 처리하지 못했습니다.');
  return payload;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[char]);
}

function setTab(button) {
  document.querySelectorAll('.tab').forEach((tab) => {
    const active = tab === button;
    tab.classList.toggle('active', active);
    tab.setAttribute('aria-selected', String(active));
  });
  document.querySelectorAll('.panel').forEach((panel) => {
    const active = panel.id === button.dataset.target;
    panel.classList.toggle('active', active);
    panel.hidden = !active;
  });
  if (button.dataset.target === 'desk') loadSchedule();
}

async function loadCounselors() {
  const result = await api('/api/counselors');
  state.counselors = result.counselors;
  const options = state.counselors.map((c) =>
    '<option value="' + escapeHtml(c.id) + '">' + escapeHtml(c.name) + ' · ' + escapeHtml(c.label) + '</option>'
  ).join('');
  $('#counselor').innerHTML = options;
  $('#admin-counselor').innerHTML = options;
}

async function loadDates() {
  const counselorId = $('#counselor').value;
  const dateSelect = $('#date');
  state.selectedSlot = null;
  $('#book').disabled = true;
  $('#book').textContent = '시간을 먼저 선택해 주세요';
  if (!counselorId) {
    dateSelect.innerHTML = '<option value="">상담자를 선택해 주세요</option>';
    dateSelect.disabled = true;
    $('#slots').innerHTML = '<p class="empty">상담자를 선택하면 가능한 시간을 보여드릴게요.</p>';
    return;
  }
  const result = await api('/api/dates?counselor_id=' + encodeURIComponent(counselorId));
  dateSelect.innerHTML = result.dates.length
    ? result.dates.map((item) => '<option value="' + item + '">' + formatDate(item) + '</option>').join('')
    : '<option value="">예약 가능한 날짜가 없습니다</option>';
  dateSelect.disabled = result.dates.length === 0;
  if (result.dates.length) await loadSlots();
  else $('#slots').innerHTML = '<p class="empty">현재 예약 가능한 시간이 없습니다.</p>';
}

async function loadSlots() {
  const counselorId = $('#counselor').value;
  const slotDate = $('#date').value;
  const grid = $('#slots');
  state.selectedSlot = null;
  $('#book').disabled = true;
  $('#book').textContent = '시간을 먼저 선택해 주세요';
  if (!counselorId || !slotDate) return;
  grid.innerHTML = '<p class="empty">가능한 시간을 확인하고 있어요.</p>';
  const result = await api('/api/slots?counselor_id=' + encodeURIComponent(counselorId) + '&date=' + encodeURIComponent(slotDate));
  if (!result.slots.length) {
    grid.innerHTML = '<p class="empty">이 날짜에는 남은 시간이 없습니다. 다른 날짜를 골라주세요.</p>';
    return;
  }
  grid.innerHTML = result.slots.map((slot) =>
    '<button class="time-slot" type="button" data-slot-id="' + slot.id + '" aria-pressed="false">' +
      '<span>' + formatTime(slot.starts_at) + '</span><small>30분</small></button>'
  ).join('');
  grid.querySelectorAll('.time-slot').forEach((button) => {
    button.addEventListener('click', () => {
      grid.querySelectorAll('.time-slot').forEach((item) => {
        item.classList.remove('selected');
        item.setAttribute('aria-pressed', 'false');
      });
      button.classList.add('selected');
      button.setAttribute('aria-pressed', 'true');
      state.selectedSlot = button.dataset.slotId;
      $('#book').disabled = false;
      $('#book').textContent = '이 시간 예약하기';
    });
  });
}

function renderBooking(booking) {
  const confirmed = booking.status === 'CONFIRMED';
  const stateClass = confirmed ? 'confirmed' : 'cancelled';
  const status = confirmed ? '예약 확정' : '취소됨';
  const cancelButton = confirmed
    ? '<button class="cancel-button" type="button">이 예약 취소</button>'
    : '';
  return '<article class="confirmation-card">' +
    '<div class="confirmation-top"><span class="status-pill ' + stateClass + '">' + status + '</span><span>' + escapeHtml(booking.counselor_label || '') + '</span></div>' +
    '<h3>' + escapeHtml(booking.client_name) + ' 님의 상담</h3>' +
    '<dl>' +
      '<div><dt>예약번호</dt><dd class="code">' + escapeHtml(booking.reference) + '</dd></div>' +
      '<div><dt>상담자</dt><dd>' + escapeHtml(booking.counselor_name) + '</dd></div>' +
      '<div><dt>일시</dt><dd>' + formatDate(booking.starts_at.slice(0, 10)) + ' · ' + formatTime(booking.starts_at) + '</dd></div>' +
      '<div><dt>시간</dt><dd>30분</dd></div>' +
    '</dl>' + cancelButton + '</article>';
}

async function loadSchedule() {
  const dateValue = $('#schedule-date').value || todayInSeoul();
  $('#schedule-date').value = dateValue;
  const list = $('#schedule');
  list.innerHTML = '<p class="empty">일정을 불러오고 있어요.</p>';
  try {
    const result = await api('/api/admin/slots?date=' + encodeURIComponent(dateValue));
    if (!result.slots.length) {
      list.innerHTML = '<p class="empty">등록된 시간이 없습니다. 왼쪽에서 새 시간을 열어주세요.</p>';
      return;
    }
    list.innerHTML = result.slots.map((slot) => {
      const booked = Boolean(slot.booking_status);
      const status = booked ? '예약 완료' : slot.is_open ? '예약 가능' : '닫힘';
      const person = booked
        ? '<span>' + escapeHtml(slot.client_name) + ' · ' + escapeHtml(slot.counselor_name) + '</span>'
        : '<span>' + escapeHtml(slot.counselor_name) + '</span>';
      const action = slot.is_open && !booked
        ? '<button class="close-slot" type="button" data-slot-id="' + slot.id + '" aria-label="' + formatTime(slot.starts_at) + ' 시간 닫기">닫기</button>'
        : '';
      const reference = slot.reference ? ' · ' + escapeHtml(slot.reference) : '';
      return '<div class="schedule-row">' +
        '<span class="schedule-time">' + formatTime(slot.starts_at) + '</span>' +
        '<span class="schedule-detail">' + person + '<small class="schedule-status ' + (booked ? 'booked' : '') + '">' + status + reference + '</small></span>' +
        action + '</div>';
    }).join('');
    list.querySelectorAll('.close-slot').forEach((button) => {
      button.addEventListener('click', async () => {
        try {
          await api('/api/admin/slots/' + button.dataset.slotId, { method: 'DELETE' });
          showMessage($('#desk-message'), '해당 시간을 닫았습니다.', 'success');
          await loadSchedule();
        } catch (error) {
          showMessage($('#desk-message'), error.message, 'error');
        }
      });
    });
  } catch (error) {
    list.innerHTML = '<p class="empty">' + escapeHtml(error.message) + '</p>';
  }
}

document.querySelectorAll('.tab').forEach((button) => {
  button.addEventListener('click', () => setTab(button));
});
$('#counselor').addEventListener('change', () => loadDates().catch((error) =>
  showMessage($('#book-message'), error.message, 'error')
));
$('#date').addEventListener('change', () => loadSlots().catch((error) =>
  showMessage($('#book-message'), error.message, 'error')
));

$('#book-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  if (!state.selectedSlot) {
    showMessage($('#book-message'), '먼저 예약 가능한 시간을 선택해 주세요.', 'error');
    return;
  }
  const button = $('#book');
  button.disabled = true;
  button.textContent = '예약을 확인하고 있어요…';
  try {
    const result = await api('/api/bookings', {
      method: 'POST',
      body: JSON.stringify({
        slot_id: state.selectedSlot,
        client_name: $('#name').value,
        email: $('#email').value
      })
    });
    const booking = result.booking;
    showMessage($('#book-message'), '예약이 확정됐습니다. 예약번호 ' + booking.reference + '를 저장해 주세요.', 'success');
    $('#reference').value = booking.reference;
    $('#lookup-email').value = $('#email').value;
    $('#book-form').reset();
    await loadDates();
  } catch (error) {
    showMessage($('#book-message'), error.message, 'error');
    button.disabled = false;
    button.textContent = '다시 시도하기';
  }
});

$('#lookup-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  $('#details').hidden = true;
  const reference = $('#reference').value.trim().toUpperCase();
  const email = $('#lookup-email').value.trim();
  try {
    const result = await api('/api/bookings/' + encodeURIComponent(reference) + '?email=' + encodeURIComponent(email));
    $('#details').innerHTML = renderBooking(result.booking);
    $('#details').hidden = false;
    showMessage($('#lookup-message'), '예약 정보를 찾았습니다.', 'success');
    const cancelButton = $('#details').querySelector('.cancel-button');
    if (cancelButton) cancelButton.addEventListener('click', async () => {
      if (!window.confirm('이 예약을 취소할까요?')) return;
      try {
        await api('/api/bookings/' + encodeURIComponent(reference) + '/cancel', {
          method: 'POST', body: JSON.stringify({ email: email })
        });
        const refreshed = await api('/api/bookings/' + encodeURIComponent(reference) + '?email=' + encodeURIComponent(email));
        $('#details').innerHTML = renderBooking(refreshed.booking);
        showMessage($('#lookup-message'), '예약을 취소했습니다.', 'success');
      } catch (error) {
        showMessage($('#lookup-message'), error.message, 'error');
      }
    });
  } catch (error) {
    showMessage($('#lookup-message'), error.message, 'error');
  }
});

$('#slot-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  try {
    await api('/api/admin/slots', {
      method: 'POST',
      body: JSON.stringify({
        counselor_id: $('#admin-counselor').value,
        date: $('#admin-date').value,
        time: $('#admin-time').value
      })
    });
    $('#schedule-date').value = $('#admin-date').value;
    showMessage($('#desk-message'), '새 예약 가능 시간을 열었습니다.', 'success');
    await loadSchedule();
  } catch (error) {
    showMessage($('#desk-message'), error.message, 'error');
  }
});
$('#schedule-date').addEventListener('change', loadSchedule);

async function start() {
  $('#admin-date').min = todayInSeoul();
  $('#admin-date').value = todayInSeoul();
  $('#schedule-date').value = todayInSeoul();
  try {
    await loadCounselors();
    await loadDates();
    if ($('#date').value) {
      $('#admin-date').value = $('#date').value;
      $('#schedule-date').value = $('#date').value;
    }
    await loadSchedule();
  } catch (error) {
    showMessage($('#book-message'), '서비스를 시작하지 못했습니다: ' + error.message, 'error');
  }
}
start();
