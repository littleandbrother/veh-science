function veh_scientist_periodic_beam_runner(input_json, output_json)
% Continuous-beam MATLAB reference for VEH Scientist.
%
% Reads a JSON config, runs the dimensional periodic Timoshenko beam model
% adapted from tr-reference/organized_code/continuum_models/new_bc.m, and
% writes the frequency response plus TR metrics back to JSON.

cfg = jsondecode(fileread(input_json));

beam.b = cfg.beam_width;
beam.h = cfg.beam_height;
beam.A = beam.b * beam.h;
beam.I = beam.b * beam.h^3 / 12;
beam.ks = 5/6;

propA.E = cfg.E_A;
propA.rho = cfg.rho_A;
propA.nu = cfg.nu_A;
propA.G = propA.E / (2 * (1 + propA.nu));

propB.E = cfg.E_B;
propB.rho = cfg.rho_B;
propB.nu = cfg.nu_B;
propB.G = propB.E / (2 * (1 + propB.nu));

pzt.h = cfg.piezo_thickness;
pzt.rho = cfg.piezo_rho;
pzt.d31 = cfg.piezo_d31;
pzt.E = cfg.piezo_E;
pzt.eps33T = cfg.piezo_eps33T;

L1 = cfg.L_A;
L2 = cfg.L_B;
a = L1 + L2;
Ncells = cfg.n_cells;
Ltot = Ncells * a;
Rload = cfg.load_resistance_ohm;

nel_A = 8;
nel_B = 2;
nel_cell = nel_A + nel_B;
Ne = Ncells * nel_cell;
Nn = Ne + 1;
Nd = 2 * Nn;
id_w = @(n) (2*n - 1);
id_phi = @(n) (2*n);

f = linspace(cfg.f_min_hz, cfg.f_max_hz, cfg.n_freq).';
omega = 2*pi*f;

K = sparse(Nd, Nd);
M = sparse(Nd, Nd);
Kme = sparse(Nd, 1);
Ke_list = cell(Ne, 1);
Me_list = cell(Ne, 1);
dof_list = cell(Ne, 1);
x_node = linspace(0, Ltot, Nn);

for e = 1:Ne
    n1 = e;
    n2 = e + 1;
    Le = x_node(n2) - x_node(n1);
    xmid = 0.5 * (x_node(n1) + x_node(n2));
    x_in_cell = mod(xmid, a);

    if x_in_cell < L1
        E = propA.E; G = propA.G; rho = propA.rho;
    else
        E = propB.E; G = propB.G; rho = propB.rho;
    end

    inPatch = (xmid >= 0.0) && (xmid <= a);
    if inPatch
        b = beam.b; hb = beam.h; hp = pzt.h; Eb = E; Ep = pzt.E;
        Ab = b * hb; Ap = b * hp;
        Ib = b * hb^3 / 12; Ip = b * hp^3 / 12;
        z_p = hb / 2 + hp / 2;
        ybar = (Eb * Ab * 0 + Ep * Ap * z_p) / (Eb * Ab + Ep * Ap);
        EIeq = Eb * (Ib + Ab * (0 - ybar)^2) + Ep * (Ip + Ap * (z_p - ybar)^2);
        Ieff = EIeq / Eb;
        rho_eff = (rho * Ab + pzt.rho * Ap) / Ab;
    else
        Ieff = beam.I;
        rho_eff = rho;
        ybar = 0;
    end

    [Ke, Me] = timoshenko_element_matrices(E, G, rho_eff, beam.A, Ieff, Le, beam.ks);
    dofs = [id_w(n1), id_phi(n1), id_w(n2), id_phi(n2)];
    K(dofs, dofs) = K(dofs, dofs) + Ke;
    M(dofs, dofs) = M(dofs, dofs) + Me;

    if inPatch
        z_p_local = beam.h/2 + pzt.h/2;
        theta_line = pzt.E * pzt.d31 * beam.b * (z_p_local - ybar);
        theta_e = theta_line * Le;
        Kme_e = theta_e * [0; -1; 0; 1];
        Kme(dofs) = Kme(dofs) + Kme_e;
    end

    Ke_list{e} = Ke;
    Me_list{e} = Me;
    dof_list{e} = dofs;
end

boundary_node = nel_A + 1;
boundary_w_dof = id_w(boundary_node);
M(boundary_w_dof, boundary_w_dof) = M(boundary_w_dof, boundary_w_dof) * cfg.boundary_mass_factor;

clamp = [id_w(1); id_phi(1)];
unknown = setdiff(1:Nd, clamp);

Kuu = K(unknown, unknown); Kux = K(unknown, clamp);
Muu = M(unknown, unknown); Mux = M(unknown, clamp);
Kme_u = Kme(unknown);      Kme_x = Kme(clamp);
Cp = pzt.eps33T * beam.b * a / pzt.h;

zeta1 = cfg.zeta1;
zeta2 = cfg.zeta2;
f1 = 0.25 * cfg.f_max_hz;
f2 = 0.80 * cfg.f_max_hz;
w1 = 2*pi*f1;
w2 = 2*pi*f2;
Aab = [1/(2*w1), w1/2; 1/(2*w2), w2/2];
ab = Aab \ [zeta1; zeta2];
alpha_ray = max(ab(1), 0);
beta_ray = max(ab(2), 0);

voltage = zeros(numel(f), 1);
power = zeros(numel(f), 1);
wL = zeros(numel(f), 1);
wR = zeros(numel(f), 1);
response_states = cell(numel(f), 1);

for k = 1:numel(f)
    [u_full, Vp] = solve_frequency_point( ...
        omega(k), ...
        cfg.excitation_type, ...
        cfg.excitation_amplitude, ...
        alpha_ray, beta_ray, cfg.tan_delta, ...
        Kuu, Kux, Muu, Mux, Kme_u, Kme_x, Cp, Rload, unknown, clamp, Nd, id_w, id_phi ...
    );

    if isempty(u_full)
        continue;
    end

    response_states{k} = u_full;
    voltage(k) = abs(Vp);
    power(k) = 0.5 * voltage(k)^2 / Rload;
    wL(k) = abs(u_full(id_w(1)));
    wR(k) = abs(u_full(id_w(Nn)));
end

transmission = 20*log10(max(wR, eps) ./ max(wL, eps));

NB = max(120, round(1.5 * numel(f)));
fB = linspace(cfg.f_min_hz, cfg.f_max_hz, NB).';
pass = false(NB, 1);
for ib = 1:NB
    wb = 2*pi*fB(ib);
    TA = timo_layer_T(propA, beam, beam.ks, L1, wb);
    TB = timo_layer_T(propB, beam, beam.ks, L2, wb);
    Tcell = TB * TA;
    ev = eig(Tcell);
    pass(ib) = any(abs(abs(ev) - 1) < 1e-3);
end
gaps = boolean_to_intervals(~pass, fB);

isGapSample = false(numel(f), 1);
for ig = 1:size(gaps, 1)
    isGapSample = isGapSample | (f >= gaps(ig, 1) & f <= gaps(ig, 2));
end

[~, iTR] = max(power .* isGapSample);
if isempty(iTR) || iTR == 0 || power(iTR) <= 0
    iTR = 1;
    fTR = 0;
    etaTR = 0;
else
    fTR = f(iTR);
    etaTR = localization_ratio(response_states{iTR}, omega(iTR), Ke_list, Me_list, dof_list, nel_cell);
end

if ~isempty(gaps)
    leftPass = f < gaps(1, 1);
else
    leftPass = true(numel(f), 1);
end
[~, iPB] = max(power .* leftPass);
if isempty(iPB) || iPB == 0
    iPB = 1;
end

result.frequency_hz = f;
result.voltage_v = voltage;
result.power_w = power;
result.w_left_m = wL;
result.w_right_m = wR;
result.transmission_db = transmission;
result.bandgaps_hz = gaps;
result.f_tr_hz = fTR;
result.f_pb1_hz = f(iPB);
result.power_tr_w = power(iTR);
result.power_pb1_w = power(iPB);
result.voltage_tr_v = voltage(iTR);
result.voltage_pb1_v = voltage(iPB);
result.pef = power(iTR) / max(power(iPB), eps);
result.eta_tr = etaTR;

fid = fopen(output_json, 'w');
fwrite(fid, jsonencode(result, PrettyPrint=true), 'char');
fclose(fid);
end


function [u_full, Vp] = solve_frequency_point(omega, excitation_type, excitation_amplitude, alpha_ray, beta_ray, tan_delta, Kuu, Kux, Muu, Mux, Kme_u, Kme_x, Cp, Rload, unknown, clamp, Nd, id_w, id_phi)
if omega < 1e-10
    u_full = [];
    Vp = [];
    return;
end

if strcmp(excitation_type, 'acceleration')
    u0_actual = excitation_amplitude / omega^2;
else
    u0_actual = excitation_amplitude;
end
uxval = [u0_actual; 0];

Cuu = alpha_ray * Muu + beta_ray * Kuu;
Cux = alpha_ray * Mux + beta_ray * Kux;
Kdyn_uu = Kuu + 1i*omega*Cuu - omega^2*Muu;
Kdyn_ux = Kux + 1i*omega*Cux - omega^2*Mux;

if tan_delta > 0
    Cp_complex = Cp * (1 - 1i*tan_delta);
else
    Cp_complex = Cp;
end
Kee = 1i*omega*Cp_complex + 1/Rload;

Kc = [Kdyn_uu,      Kme_u; ...
      1i*omega*Kme_u.', Kee];
Rc = [-Kdyn_ux * uxval; -1i*omega*(Kme_x.' * uxval)];

coln = sqrt(sum(abs(Kc).^2, 1)).';
coln(coln == 0) = 1;
Dcol = spdiags(1 ./ coln, 0, size(Kc, 2), size(Kc, 2));
Kcs = Kc * Dcol;
tau = 1e-8 * norm(Kcs, 'fro');
xs = (Kcs' * Kcs + (tau^2) * speye(size(Kcs, 2))) \ (Kcs' * Rc);
Uc = Dcol * xs;

uf = Uc(1:end-1);
Vp = Uc(end);
u_full = zeros(Nd, 1);
u_full(unknown) = uf;
u_full(id_w(1)) = uxval(1);
u_full(id_phi(1)) = uxval(2);
end


function eta = localization_ratio(u_full, omega, Ke_list, Me_list, dof_list, nel_cell)
Etot = 0;
Efirst = 0;
for e = 1:numel(Ke_list)
    ue = u_full(dof_list{e});
    Ekin = 0.25 * omega^2 * real(ue' * Me_list{e} * ue);
    Estr = 0.25 * real(ue' * Ke_list{e} * ue);
    Eelem = max(Ekin + Estr, 0);
    Etot = Etot + Eelem;
    if e <= nel_cell
        Efirst = Efirst + Eelem;
    end
end
if Etot <= 0
    eta = 0;
else
    eta = Efirst / Etot;
end
end


function [Ke, Me] = timoshenko_element_matrices(E, G, rho, A, I, L, ks)
phi = (12 * E * I) / (ks * G * A * L^2);
Ke = (E * I / (L^3 * (1 + phi))) * ...
    [12, 6*L, -12, 6*L; ...
     6*L, (4+phi)*L^2, -6*L, (2-phi)*L^2; ...
     -12, -6*L, 12, -6*L; ...
     6*L, (2-phi)*L^2, -6*L, (4+phi)*L^2];
m1 = rho * A * L / 420;
m2 = rho * I * L / 420;
Me_t = m1 * [156,22*L,54,-13*L; 22*L,4*L^2,13*L,-3*L^2; 54,13*L,156,-22*L; -13*L,-3*L^2,-22*L,4*L^2];
Me_r = m2 * [36,3*L,-36,3*L; 3*L,4*L^2,-3*L,-1*L^2; -36,-3*L,36,-3*L; 3*L,-1*L^2,-3*L,4*L^2];
Me = Me_t + Me_r;
end


function U = timo_layer_T(prop, beam, ks, L, omega)
E = prop.E; G = prop.G; rho = prop.rho;
A = beam.A; I = beam.I; kGA = ks * G * A;
Am = [0, 1, 1/kGA, 0; ...
      0, 0, 0, 1/(E*I); ...
      -omega^2*rho*A, 0, 0, 0; ...
      0, -omega^2*rho*I, -1, 0];
U = expm(Am * L);
end


function gaps = boolean_to_intervals(mask, fgrid)
gaps = [];
dm = diff([false; mask(:); false]);
iStart = find(dm == 1);
iEnd = find(dm == -1) - 1;
for k = 1:numel(iStart)
    gaps = [gaps; fgrid(iStart(k)), fgrid(iEnd(k))]; %#ok<AGROW>
end
end
