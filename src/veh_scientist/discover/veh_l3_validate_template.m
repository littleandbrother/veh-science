function veh_l3_validate(input_json_path, output_json_path)
raw = fileread(input_json_path);
data = jsondecode(raw);

result = struct();
result.protocol_version = 'l3-protocol-1.0';
result.status = 'failed';
result.engine = 'matlab-live-link';
result.notes = '';
result.frequency_pairs = struct([]);
result.stopband_pairs = struct([]);
result.anchor_alignment = struct([]);
result.curve_artifacts = struct();

backend = get_field(data, 'backend_config', struct());
solver_controls = get_field(data, 'solver_controls', struct());
host = getenv('VEHSCI_COMSOL_SERVER_HOST');
port_text = getenv('VEHSCI_COMSOL_SERVER_PORT');

if isempty(host) || isempty(port_text)
    result.notes = 'Missing COMSOL server host/port for MATLAB LiveLink.';
    write_result(output_json_path, result);
    return
end

model_path = char(get_field(backend, 'comsol_model_path', ''));
if isempty(model_path)
    result.notes = 'No COMSOL model_path was provided in the request manifest.';
    write_result(output_json_path, result);
    return
end

study_tag = char(get_field(backend, 'comsol_study_tag', 'std_freq'));
dataset_tag = char(get_field(backend, 'comsol_dataset_tag', 'dset2'));
sweep_hz = get_field(solver_controls, 'frequency_sweep_hz', []);
step_hz = to_scalar(get_field(solver_controls, 'frequency_step_hz', 50.0), 50.0);
parameter_overrides = get_field(solver_controls, 'parameter_overrides', struct());
output_dir = fileparts(char(output_json_path));

try
    mphstart(host, str2double(port_text));
    model = mphload(model_path);
    apply_parameter_overrides(model, parameter_overrides);
    if numel(sweep_hz) >= 2
        plist = sprintf('range(%g[Hz],%g[Hz],%g[Hz])', sweep_hz(1), step_hz, sweep_hz(2));
        model.study(study_tag).feature('freq').set('plist', plist);
    end
    model.study(study_tag).run;

    freq = double(mphglobal(model, 'freq', 'dataset', dataset_tag));
    voltage = mphglobal(model, 'es.V0_1', 'dataset', dataset_tag);
    freq = freq(:);
    voltage = voltage(:);
    amplitude = abs(voltage);
    peak_mask = find_local_peaks(amplitude);
    if ~any(peak_mask)
        [~, max_index] = max(amplitude);
        peak_mask(max_index) = true;
    end

    peak_freqs = freq(peak_mask);
    peak_values = amplitude(peak_mask);
    [frequency_pairs, alignments] = build_frequency_pairs(data, peak_freqs, peak_values);

    [field_data, field_notes] = try_extract_field_solution(model, dataset_tag, numel(freq));
    if ~isempty(field_data.disp_matrix)
        output_mask = downstream_mask(field_data.x_coords);
        transmission_response = mean(field_data.disp_matrix(:, output_mask), 2);
        transmission_definition = 'mean solid.disp over the downstream x>=95th percentile slice';
    else
        transmission_response = amplitude;
        transmission_definition = 'abs(es.V0_1) fallback because solid.disp extraction was unavailable';
    end

    transmission_db = normalized_db(transmission_response);
    smoothed_db = rolling_median(transmission_db, 5);
    threshold_db = derive_threshold_db(data);
    detected_stopbands = detect_stopbands(freq, smoothed_db, threshold_db);
    stopband_pairs = build_stopband_pairs(data, alignments, detected_stopbands);

    resistance_ohm = load_resistance_ohm(data);
    power_mw = (amplitude .^ 2) ./ (2.0 * resistance_ohm) * 1.0e3;
    transmission_curve_path = write_curve_csv( ...
        fullfile(output_dir, 'transmission_curve.csv'), ...
        {'frequency_hz', 'transmission_disp', 'transmission_db', 'smoothed_transmission_db'}, ...
        [freq, transmission_response, transmission_db, smoothed_db] ...
    );
    power_curve_path = write_curve_csv( ...
        fullfile(output_dir, 'power_curve.csv'), ...
        {'frequency_hz', 'terminal_voltage_real', 'terminal_voltage_imag', 'terminal_voltage_abs', 'power_mw'}, ...
        [freq, real(voltage), imag(voltage), amplitude, power_mw] ...
    );
    stopband_summary_path = fullfile(output_dir, 'stopband_summary.json');
    stopband_summary = struct( ...
        'threshold_transmission_db', threshold_db, ...
        'detected_stopbands_hz', detected_stopbands ...
    );
    write_json_file(stopband_summary_path, stopband_summary);

    [mode_shape_summary_path, mode_shape_profiles, mode_shape_notes] = write_mode_shape_profiles( ...
        output_dir, ...
        freq, ...
        alignments, ...
        field_data ...
    );

    result.status = ternary(~isempty(frequency_pairs), 'passed', 'failed');
    result.frequency_pairs = frequency_pairs;
    result.stopband_pairs = stopband_pairs;
    result.anchor_alignment = alignments;
    result.notes = sprintf( ...
        'MATLAB LiveLink executed COMSOL model %s and evaluated %d frequency points. %s %s', ...
        model_path, ...
        numel(freq), ...
        field_notes, ...
        mode_shape_notes ...
    );
    result.curve_artifacts = struct( ...
        'study_tag', study_tag, ...
        'dataset_tag', dataset_tag, ...
        'peak_count', numel(peak_freqs), ...
        'peak_frequencies_hz', reshape(double(peak_freqs), 1, []), ...
        'observed_frequency_span_hz', [double(freq(1)), double(freq(end))], ...
        'transmission_curve', transmission_curve_path, ...
        'power_curve', power_curve_path, ...
        'mode_shape', mode_shape_summary_path, ...
        'mode_shape_profiles', mode_shape_profiles, ...
        'stopband_summary', stopband_summary_path, ...
        'threshold_transmission_db', threshold_db, ...
        'detected_stopbands_hz', detected_stopbands, ...
        'transmission_definition', transmission_definition, ...
        'power_definition', 'abs(es.V0_1)^2 / (2*RL_ohm)' ...
    );
catch ME
    result.status = 'failed';
    result.notes = sprintf('MATLAB LiveLink execution failed: %s', ME.message);
end

write_result(output_json_path, result);
end


function apply_parameter_overrides(model, overrides)
fields = fieldnames(overrides);
for idx = 1:numel(fields)
    name = fields{idx};
    value = overrides.(name);
    if isempty(value)
        continue
    end
    try
        model.param.set(name, format_parameter_value(name, value));
    catch
    end
end
end


function text = format_parameter_value(name, value)
units = struct( ...
    'L_A', '[m]', ...
    'L_B', '[m]', ...
    'a_cell', '[m]', ...
    'bw', '[m]', ...
    'hs', '[m]', ...
    'hp', '[m]', ...
    'a_exc', '[m/s^2]', ...
    'RL_ohm', '[ohm]', ...
    'f_exc_hz', '[Hz]' ...
);
if isfield(units, name)
    text = sprintf('%g%s', double(value), units.(name));
else
    text = sprintf('%g', double(value));
end
end


function [pairs, alignments] = build_frequency_pairs(data, peak_freqs, peak_values)
anchors = get_field(data, 'anchor_targets', struct([]));
candidates = get_field(data, 'candidate_targets', struct([]));

pairs = struct('band_index', {}, 'label', {}, 'raw_frequency_hz', {}, 'l3_frequency_hz', {}, 'source', {});
alignments = struct('label', {}, 'anchor_frequency_hz', {}, 'best_frequency_hz', {}, 'error_hz', {}, 'response_amplitude', {});

for idx = 1:numel(anchors)
    anchor = anchors(idx);
    anchor_hz = to_scalar(get_field(anchor, 'frequency_hz', NaN), NaN);
    if isnan(anchor_hz)
        continue
    end
    [peak_hz, response_amplitude] = nearest_peak(anchor_hz, peak_freqs, peak_values);
    if isnan(peak_hz)
        continue
    end
    candidate = match_candidate(candidates, anchor_hz, get_field(anchor, 'band_index', 0));
    raw_frequency_hz = peak_hz;
    band_index = to_scalar(get_field(anchor, 'band_index', 0), 0);
    if ~isempty(candidate)
        raw_frequency_hz = to_scalar(get_field(candidate, 'raw_frequency_hz', get_field(candidate, 'frequency_hz', peak_hz)), peak_hz);
        if band_index <= 0
            band_index = to_scalar(get_field(candidate, 'band_index', 0), 0);
        end
    end
    label = char(get_field(anchor, 'label', sprintf('TR%d', idx)));
    pairs(end + 1) = struct( ...
        'band_index', double(band_index), ...
        'label', label, ...
        'raw_frequency_hz', double(raw_frequency_hz), ...
        'l3_frequency_hz', double(peak_hz), ...
        'source', 'matlab-live-link' ...
    );
    alignments(end + 1) = struct( ...
        'label', label, ...
        'anchor_frequency_hz', double(anchor_hz), ...
        'best_frequency_hz', double(peak_hz), ...
        'error_hz', double(abs(peak_hz - anchor_hz)), ...
        'response_amplitude', double(response_amplitude) ...
    );
end
end


function candidate = match_candidate(candidates, anchor_hz, band_index)
candidate = [];
if isempty(candidates)
    return
end
for idx = 1:numel(candidates)
    candidate_band = to_scalar(get_field(candidates(idx), 'band_index', 0), 0);
    if band_index > 0 && candidate_band == band_index
        candidate = candidates(idx);
        return
    end
end
best_error = inf;
for idx = 1:numel(candidates)
    raw_hz = to_scalar(get_field(candidates(idx), 'raw_frequency_hz', get_field(candidates(idx), 'frequency_hz', NaN)), NaN);
    if isnan(raw_hz)
        continue
    end
    error_hz = abs(raw_hz - anchor_hz);
    if error_hz < best_error
        best_error = error_hz;
        candidate = candidates(idx);
    end
end
end


function [peak_hz, response_amplitude] = nearest_peak(anchor_hz, peak_freqs, peak_values)
peak_hz = NaN;
response_amplitude = NaN;
if isempty(peak_freqs)
    return
end
[~, index] = min(abs(double(peak_freqs) - double(anchor_hz)));
peak_hz = double(peak_freqs(index));
response_amplitude = double(peak_values(index));
end


function mask = find_local_peaks(values)
n = numel(values);
mask = false(size(values));
if n == 0
    return
elseif n == 1
    mask(1) = true;
    return
end
mask(2:n-1) = values(2:n-1) >= values(1:n-2) & values(2:n-1) > values(3:n);
end


function db = normalized_db(values)
values = double(values(:));
if isempty(values)
    db = values;
    return
end
reference = max(max(abs(values)), 1.0e-12);
db = 20.0 * log10(max(abs(values), 1.0e-12) / reference);
end


function filtered = rolling_median(values, window)
values = double(values(:));
if nargin < 2 || window <= 1 || isempty(values)
    filtered = values;
    return
end
if exist('movmedian', 'builtin') || exist('movmedian', 'file')
    filtered = movmedian(values, window);
    return
end
radius = floor(window / 2);
filtered = zeros(size(values));
for idx = 1:numel(values)
    lo = max(1, idx - radius);
    hi = min(numel(values), idx + radius);
    filtered(idx) = median(values(lo:hi));
end
end


function threshold_db = derive_threshold_db(data)
anchors = get_field(data, 'anchor_targets', struct([]));
values = [];
for idx = 1:numel(anchors)
    target = to_scalar(get_field(anchors(idx), 'target_transmission_db', NaN), NaN);
    if ~isnan(target)
        values(end + 1) = target; %#ok<AGROW>
    end
end
if isempty(values)
    threshold_db = -6.0;
else
    threshold_db = min([min(values), -6.0]);
end
end


function intervals = detect_stopbands(freq, transmission_db, threshold_db)
freq = double(freq(:));
transmission_db = double(transmission_db(:));
intervals = zeros(0, 2);
if isempty(freq) || isempty(transmission_db)
    return
end
mask = transmission_db <= threshold_db;
start_idx = 0;
for idx = 1:numel(mask)
    if mask(idx) && start_idx == 0
        start_idx = idx;
    elseif ~mask(idx) && start_idx > 0
        if idx - start_idx >= 2
            intervals(end + 1, :) = [freq(start_idx), freq(idx - 1)]; %#ok<AGROW>
        end
        start_idx = 0;
    end
end
if start_idx > 0 && numel(mask) - start_idx + 1 >= 2
    intervals(end + 1, :) = [freq(start_idx), freq(end)]; %#ok<AGROW>
end
end


function stopband_pairs = build_stopband_pairs(data, alignments, detected_stopbands)
anchors = get_field(data, 'anchor_targets', struct([]));
candidates = get_field(data, 'candidate_targets', struct([]));
stopband_pairs = struct('band_index', {}, 'label', {}, 'raw_stopband_hz', {}, 'l3_stopband_hz', {}, 'source', {});

for idx = 1:numel(anchors)
    anchor = anchors(idx);
    label = char(get_field(anchor, 'label', sprintf('TR%d', idx)));
    anchor_hz = to_scalar(get_field(anchor, 'frequency_hz', NaN), NaN);
    band_index = to_scalar(get_field(anchor, 'band_index', 0), 0);
    if isnan(anchor_hz)
        continue
    end
    candidate = match_candidate(candidates, anchor_hz, band_index);
    if isempty(candidate)
        continue
    end
    raw_stopband = get_field(candidate, 'raw_stopband_hz', []);
    if isempty(raw_stopband) || numel(raw_stopband) < 2
        continue
    end
    observed_hz = anchor_hz;
    for align_idx = 1:numel(alignments)
        if strcmp(char(get_field(alignments(align_idx), 'label', '')), label)
            observed_hz = to_scalar(get_field(alignments(align_idx), 'best_frequency_hz', anchor_hz), anchor_hz);
            break
        end
    end
    interval = match_stopband_interval(detected_stopbands, anchor_hz, observed_hz);
    interval = refine_stopband_interval(interval, anchor, detected_stopbands);
    if isempty(interval)
        continue
    end
    stopband_pairs(end + 1) = struct( ... %#ok<AGROW>
        'band_index', double(band_index), ...
        'label', label, ...
        'raw_stopband_hz', reshape(double(raw_stopband(1:2)), 1, []), ...
        'l3_stopband_hz', reshape(double(interval(1:2)), 1, []), ...
        'source', 'matlab-live-link' ...
    );
end
end


function interval = match_stopband_interval(intervals, anchor_hz, observed_hz)
interval = [];
if isempty(intervals)
    return
end
targets = [observed_hz, anchor_hz];
for value = targets
    for idx = 1:size(intervals, 1)
        if intervals(idx, 1) <= value && value <= intervals(idx, 2)
            interval = intervals(idx, :);
            return
        end
    end
end
target = targets(1);
best_error = inf;
for idx = 1:size(intervals, 1)
    center = 0.5 * (intervals(idx, 1) + intervals(idx, 2));
    error_value = abs(center - target);
    if error_value < best_error
        best_error = error_value;
        interval = intervals(idx, :);
    end
end
end


function resistance_ohm = load_resistance_ohm(data)
solver_controls = get_field(data, 'solver_controls', struct());
overrides = get_field(solver_controls, 'parameter_overrides', struct());
resistance_ohm = to_scalar(get_field(overrides, 'RL_ohm', 1.0), 1.0);
resistance_ohm = max(resistance_ohm, 1.0);
end


function interval = refine_stopband_interval(interval, anchor, detected_stopbands)
hint = get_field(anchor, 'stopband_hz', []);
if isempty(hint) || numel(hint) < 2
    return
end
hint = reshape(double(hint(1:2)), 1, []);
if isempty(interval)
    interval = hint;
    return
end
sweep_min = hint(1);
sweep_max = hint(2);
if ~isempty(detected_stopbands)
    sweep_min = min(detected_stopbands(:, 1));
    sweep_max = max(detected_stopbands(:, 2));
end
interval_width = interval(2) - interval(1);
hint_width = max(hint(2) - hint(1), 1.0);
sweep_width = max(sweep_max - sweep_min, 1.0);
if interval_width >= 0.85 * sweep_width || interval_width >= 2.0 * hint_width
    interval = [max(sweep_min, hint(1)), min(sweep_max, hint(2))];
end
end


function [field_data, notes] = try_extract_field_solution(model, dataset_tag, n_freq)
field_data = struct( ...
    'disp_matrix', [], ...
    'x_coords', [], ...
    'y_coords', [], ...
    'z_coords', [], ...
    'w_matrix', [] ...
);
notes = 'field extraction unavailable.';
try
    disp_eval = mpheval(model, 'solid.disp', 'dataset', dataset_tag);
    disp_matrix = orient_solution_matrix(double(disp_eval.d1), n_freq);
    coordinates = double(disp_eval.p);
    if isempty(coordinates)
        error('No coordinates returned by mpheval.');
    end
    field_data.disp_matrix = disp_matrix;
    field_data.x_coords = coordinates(1, :);
    if size(coordinates, 1) >= 2
        field_data.y_coords = coordinates(2, :);
    else
        field_data.y_coords = zeros(1, size(coordinates, 2));
    end
    if size(coordinates, 1) >= 3
        field_data.z_coords = coordinates(3, :);
    else
        field_data.z_coords = zeros(1, size(coordinates, 2));
    end
    try
        w_eval = mpheval(model, 'w', 'dataset', dataset_tag);
        field_data.w_matrix = orient_solution_matrix(abs(double(w_eval.d1)), n_freq);
    catch
        field_data.w_matrix = [];
    end
    notes = sprintf('Extracted field data over %d mesh points.', numel(field_data.x_coords));
catch ME
    notes = sprintf('field extraction unavailable (%s).', ME.message);
end
end


function matrix = orient_solution_matrix(values, n_freq)
matrix = double(values);
if isempty(matrix)
    matrix = zeros(n_freq, 0);
    return
end
if size(matrix, 1) == n_freq
    return
end
if size(matrix, 2) == n_freq
    matrix = matrix.';
    return
end
matrix = reshape(matrix, n_freq, []);
end


function mask = downstream_mask(x_coords)
x_coords = double(x_coords(:));
threshold = prctile(x_coords, 95);
mask = x_coords >= threshold;
if ~any(mask)
    mask = true(size(x_coords));
end
end


function path = write_curve_csv(path, headers, matrix)
fid = fopen(path, 'w');
if fid < 0
    error('Unable to open CSV path for writing: %s', path);
end
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, '%s\n', strjoin(headers, ','));
for row_idx = 1:size(matrix, 1)
    values = matrix(row_idx, :);
    format_parts = repmat({'%.12g'}, 1, numel(values));
    fprintf(fid, [strjoin(format_parts, ','), '\n'], values);
end
path = char(java.io.File(path).getCanonicalPath());
end


function [summary_path, profile_paths, notes] = write_mode_shape_profiles(output_dir, freq, alignments, field_data)
summary_path = '';
profile_paths = struct();
notes = 'mode shape extraction skipped.';
if isempty(field_data.disp_matrix) || isempty(alignments)
    return
end

x_coords = double(field_data.x_coords(:));
y_coords = double(field_data.y_coords(:));
z_coords = double(field_data.z_coords(:));
disp_matrix = double(field_data.disp_matrix);
w_matrix = double(field_data.w_matrix);
bin_edges = linspace(min(x_coords), max(x_coords), 161);
profiles = struct([]);

for idx = 1:numel(alignments)
    label = char(get_field(alignments(idx), 'label', sprintf('mode_%d', idx)));
    frequency_hz = to_scalar(get_field(alignments(idx), 'best_frequency_hz', NaN), NaN);
    if isnan(frequency_hz)
        continue
    end
    [~, freq_index] = min(abs(double(freq(:)) - frequency_hz));
    disp_slice = disp_matrix(freq_index, :).';
    if isempty(w_matrix)
        w_slice = [];
    else
        w_slice = w_matrix(freq_index, :).';
    end
    rows = zeros(0, 8);
    for bin_idx = 1:numel(bin_edges) - 1
        left_edge = bin_edges(bin_idx);
        right_edge = bin_edges(bin_idx + 1);
        if bin_idx == numel(bin_edges) - 1
            mask = x_coords >= left_edge & x_coords <= right_edge;
        else
            mask = x_coords >= left_edge & x_coords < right_edge;
        end
        if ~any(mask)
            continue
        end
        disp_bin = disp_slice(mask);
        if isempty(w_slice)
            w_mean = NaN;
            w_max = NaN;
        else
            w_mean = mean(w_slice(mask));
            w_max = max(w_slice(mask));
        end
        rows(end + 1, :) = [ ... %#ok<AGROW>
            mean(x_coords(mask)), ...
            mean(y_coords(mask)), ...
            mean(z_coords(mask)), ...
            mean(disp_bin), ...
            max(disp_bin), ...
            sum(mask), ...
            w_mean, ...
            w_max ...
        ];
    end
    if isempty(rows)
        continue
    end
    safe_label = sanitize_label(label);
    profile_path = write_curve_csv( ...
        fullfile(output_dir, sprintf('mode_shape_%s.csv', safe_label)), ...
        {'x_m', 'y_m', 'z_m', 'disp_mean', 'disp_max', 'point_count', 'w_abs_mean', 'w_abs_max'}, ...
        rows ...
    );
    profile_paths.(safe_label) = profile_path;
    profile = struct( ...
        'label', label, ...
        'frequency_hz', double(freq(freq_index)), ...
        'profile_path', profile_path, ...
        'max_disp', double(max(disp_slice)), ...
        'peak_x_m', double(x_coords(argmax(disp_slice))) ...
    );
    if isempty(profiles)
        profiles = profile;
    else
        profiles(end + 1) = profile; %#ok<AGROW>
    end
end

if isempty(profiles)
    notes = 'mode shape extraction skipped because no profile rows were produced.';
    return
end
summary_path = fullfile(output_dir, 'mode_shape_summary.json');
write_json_file(summary_path, struct('profiles', profiles));
summary_path = char(java.io.File(summary_path).getCanonicalPath());
notes = sprintf('mode shape profiles written for %d anchors.', numel(profiles));
end


function index = argmax(values)
[~, index] = max(values);
end


function text = sanitize_label(label)
text = regexprep(char(label), '[^A-Za-z0-9_-]', '_');
if isempty(text)
    text = 'anchor';
end
end


function value = get_field(source, field_name, fallback)
if isstruct(source) && isfield(source, field_name)
    value = source.(field_name);
else
    value = fallback;
end
end


function value = to_scalar(input_value, fallback)
if isempty(input_value)
    value = fallback;
elseif isnumeric(input_value)
    value = double(input_value(1));
else
    parsed = str2double(string(input_value));
    if isnan(parsed)
        value = fallback;
    else
        value = parsed;
    end
end
end


function output = ternary(condition, left_value, right_value)
if condition
    output = left_value;
else
    output = right_value;
end
end


function write_json_file(path, payload)
fid = fopen(path, 'w');
if fid < 0
    error('Unable to open JSON path for writing: %s', path);
end
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, '%s', jsonencode(payload));
end


function write_result(output_json_path, payload)
write_json_file(char(output_json_path), payload);
end
