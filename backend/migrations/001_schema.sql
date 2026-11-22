CREATE TABLE IF NOT EXISTS users (
  id SERIAL PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  role TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS course_classes (
  id SERIAL PRIMARY KEY,
  code TEXT UNIQUE NOT NULL,
  course_name TEXT NOT NULL,
  department TEXT NOT NULL,
  term TEXT NOT NULL,
  weekday INTEGER NOT NULL CHECK (weekday BETWEEN 1 AND 7),
  start_time TIME NOT NULL,
  end_time TIME NOT NULL,
  room TEXT NOT NULL,
  expected_hours NUMERIC(5,2) NOT NULL CHECK (expected_hours > 0 AND expected_hours <= 8),
  teacher_id INTEGER REFERENCES users(id),
  status TEXT NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS work_records (
  id SERIAL PRIMARY KEY,
  class_id INTEGER NOT NULL REFERENCES course_classes(id),
  ta_id INTEGER NOT NULL REFERENCES users(id),
  work_date DATE NOT NULL,
  check_in TIMESTAMPTZ,
  check_out TIMESTAMPTZ,
  activity_type TEXT NOT NULL,
  work_description TEXT NOT NULL,
  reported_hours NUMERIC(5,2) NOT NULL CHECK (reported_hours > 0 AND reported_hours <= 12),
  validated_hours NUMERIC(5,2) NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'draft',
  conflict_type TEXT,
  review_note TEXT,
  teacher_id INTEGER REFERENCES users(id),
  reviewed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS work_record_natural_key ON work_records(class_id, ta_id, work_date, activity_type);
CREATE INDEX IF NOT EXISTS work_records_ta_time ON work_records(ta_id, check_in, check_out);
CREATE INDEX IF NOT EXISTS work_records_status ON work_records(status);

-- 同一助教跨学院签到时段重叠时，只允许一笔进入计薪。冲突对与每次学院裁决都单独留痕。
CREATE TABLE IF NOT EXISTS adjudication_cases (
  id SERIAL PRIMARY KEY,
  ta_id INTEGER NOT NULL REFERENCES users(id),
  record_a_id INTEGER NOT NULL REFERENCES work_records(id),
  record_b_id INTEGER NOT NULL REFERENCES work_records(id),
  winner_record_id INTEGER REFERENCES work_records(id),
  status TEXT NOT NULL DEFAULT 'pending',
  version INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (record_a_id <> record_b_id),
  UNIQUE(record_a_id, record_b_id)
);
CREATE INDEX IF NOT EXISTS adjudication_cases_ta ON adjudication_cases(ta_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS adjudication_decisions (
  id SERIAL PRIMARY KEY,
  case_id INTEGER NOT NULL REFERENCES adjudication_cases(id),
  seq INTEGER NOT NULL,
  actor_id INTEGER REFERENCES users(id),
  chosen_record_id INTEGER NOT NULL REFERENCES work_records(id),
  previous_record_id INTEGER REFERENCES work_records(id),
  reason TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  response_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(case_id, seq),
  UNIQUE(case_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS approval_sheets (
  id SERIAL PRIMARY KEY,
  department TEXT NOT NULL,
  month TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft',
  totals_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  published_at TIMESTAMPTZ,
  approved_by INTEGER REFERENCES users(id),
  UNIQUE(department, month)
);
CREATE TABLE IF NOT EXISTS audit_logs (
  id SERIAL PRIMARY KEY,
  actor_id INTEGER REFERENCES users(id),
  action TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id INTEGER,
  detail_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
