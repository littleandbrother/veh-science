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

try
    mphstart(host, str2double(port_text));
    model = mphload(model_path);
    apply_parameter_overrides(model, parameter_overrides);
    if numel(sweep_hz) >= 2
        plist = sprintf('range(%g[Hz],%g[Hz],%g[Hz])', sweep_hz(1), step_hz, sweep_hz(2));
        model.study(study_tag).feature('freq').set('plist', plist);
    end
    model.study(study_tag).run;

    freq = mphglobal(model, 'freq', 'dataset', dataset_tag);
    voltage = mphglobal(model, 'es.V0_1', 'dataset', dataset_tag);
    freq = freq(:);
    amplitude = abs(voltage(:));
    peak_mask = find_local_peaks(amplitude);
    if ~any(peak_mask)
        [~, max_index] = max(amplitude);
        peak_mask(max_index) = true;
    end

    peak_freqs = freq(peak_mask);
    peak_values = amplitude(peak_mask);
    [frequency_pairs, alignments] = build_frequency_pairs(data, peak_freqs, peak_values);

    result.status = ternary(~isempty(frequency_pairs), 'passed', 'failed');
    result.frequency_pairs = frequency_pairs;
    result.anchor_alignment = alignments;
    result.notes = sprintf('MATLAB LiveLink executed COMSOL model %s and evaluated %d frequency points.', model_path, numel(freq));
    result.curve_artifacts = struct( ...
        'study_tag', study_tag, ...
        'dataset_tag', dataset_tag, ...
        'peak_count', numel(peak_freqs), ...
        'peak_frequencies_hz', reshape(double(peak_freqs), 1, []), ...
        'observed_frequency_span_hz', [double(freq(1)), double(freq(end))] ...
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


function write_result(output_json_path, payload)
fid = fopen(char(output_json_path), 'w');
if fid < 0
    error('Unable to open result path for writing: %s', char(output_json_path));
end
fprintf(fid, '%s', jsonencode(payload));
fclose(fid);
end
