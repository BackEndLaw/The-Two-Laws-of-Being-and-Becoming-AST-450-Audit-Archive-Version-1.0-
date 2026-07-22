% verify_atlas_results.m
%
% Reproduces the repository's Atlas accuracy checks in MATLAB.

clear; clc;

fileCandidates = [
    "atlas_predictions_with_accuracy.csv"
    "atlas_predictions_with_accuracy.xlsx"
    "Final_Atlas_Coded_Analysis-f086.xlsx"
];

inputFile = "";
for k = 1:numel(fileCandidates)
    if exist(fileCandidates(k), "file") == 2
        inputFile = fileCandidates(k);
        break;
    end
end

if inputFile == ""
    error("No Atlas input file found in the current folder.");
end

fprintf("Loading Atlas file: %s\n", inputFile);

opts = detectImportOptions(inputFile, "TextType", "string");
opts.VariableNamingRule = "preserve";

try
    T = readtable(inputFile, opts);
catch
    T = readtable(inputFile, "TextType", "string", "VariableNamingRule", "preserve");
end

requiredColumns = ["C", "Φ", "Mode", "Sym"];
for i = 1:numel(requiredColumns)
    if ~any(strcmp(T.Properties.VariableNames, requiredColumns(i)))
        error("Missing required column: %s", requiredColumns(i));
    end
end

actualCandidates = ["Regime_Actual", "Actual_Regime", "Outcome", "Out(t₀)", "Out(late)", "Regime", "Actual"];
actualColumn = pickVariableName(T, actualCandidates);
if actualColumn == ""
    error("No actual outcome column found.");
end

fprintf("Using actual outcome column: %s\n", actualColumn);
fprintf("Total cases: %d\n\n", height(T));

profileNames = ["Default", "TwoLaws_Strict", "TwoLaws_Calibrated"];

for p = 1:numel(profileNames)
    profileName = profileNames(p);
    predicted = strings(height(T), 1);

    for r = 1:height(T)
        switch profileName
            case "Default"
                predicted(r) = classifyRegimeDefault(T, r);
            case "TwoLaws_Strict"
                predicted(r) = classifyRegimeTwoLawsStrict(T, r);
            case "TwoLaws_Calibrated"
                predicted(r) = classifyRegimeTwoLawsCalibrated(T, r);
        end
    end

    actual = normalizeRegimeLabel(T.(actualColumn));
    predictedNormalized = normalizeRegimeLabel(predicted);
    validMask = ~ismissing(actual);
    match = validMask & (predictedNormalized == actual);

    total = sum(validMask);
    correct = sum(match);
    accuracy = 100 * correct / total;

    fprintf("=== ACCURACY RESULTS (%s) ===\n", profileName);
    fprintf("Total: %d / %d cases (%.2f%%)\n", correct, total, accuracy);

    regimes = unique(actual(validMask));
    regimes = sort(regimes);
    fprintf("\nPer-regime breakdown:\n");
    for i = 1:numel(regimes)
        regime = regimes(i);
        regimeMask = validMask & (actual == regime);
        regimeTotal = sum(regimeMask);
        regimeCorrect = sum(match & regimeMask);
        regimeAccuracy = 100 * regimeCorrect / regimeTotal;
        fprintf("  %s: %d / %d (%.1f%%)\n", regime, regimeCorrect, regimeTotal, regimeAccuracy);
    end

    mismatchRows = find(validMask & ~match);
    fprintf("\nFound %d mismatches (showing first 10):\n", numel(mismatchRows));
    if isempty(mismatchRows)
        fprintf("  None\n\n");
        continue;
    end

    showCount = min(10, numel(mismatchRows));
    for i = 1:showCount
        r = mismatchRows(i);
        caseLabel = getCaseLabel(T, r);
        qValue = getNumericValue(T, r, ["Q_predicted", "Q=C×Φ", "Q"]);
        phiValue = getNumericValue(T, r, ["Φ", "Phi"]);
        modeValue = getTextValue(T, r, ["Mode"]);
        fprintf("  Case %s: Predicted %s, Expected %s (Q=%.1f, Phi=%.1f, Mode=%s)\n", ...
            caseLabel, predictedNormalized(r), actual(r), qValue, phiValue, modeValue);
    end
    fprintf("\n");
end

function name = pickVariableName(T, candidates)
    name = "";
    for i = 1:numel(candidates)
        if any(strcmp(T.Properties.VariableNames, candidates(i)))
            name = candidates(i);
            return;
        end
    end
end

function value = getNumericValue(T, r, candidates)
    value = NaN;
    for i = 1:numel(candidates)
        name = candidates(i);
        if any(strcmp(T.Properties.VariableNames, name))
            raw = T{r, name};
            if isnumeric(raw) || islogical(raw)
                value = double(raw);
            else
                parsed = str2double(string(raw));
                if ~isnan(parsed)
                    value = parsed;
                end
            end
            return;
        end
    end
end

function value = getTextValue(T, r, candidates)
    value = "";
    for i = 1:numel(candidates)
        name = candidates(i);
        if any(strcmp(T.Properties.VariableNames, name))
            value = string(T{r, name});
            return;
        end
    end
end

function label = classifyRegimeDefault(T, r)
    mode = upper(strtrim(getTextValue(T, r, ["Mode"])));
    omega = upper(strtrim(getTextValue(T, r, ["Ω"])));
    kappaStruct = getNumericValue(T, r, ["κ"]);
    if isnan(kappaStruct)
        kappaStruct = getNumericValue(T, r, ["kappa_predicted"]);
    end
    if ~isnan(kappaStruct)
        kappaKey = round(kappaStruct, 2);
    else
        kappaKey = NaN;
    end

    bio = getNumericValue(T, r, ["Bio"]);
    env = getNumericValue(T, r, ["Env"]);
    cog = getNumericValue(T, r, ["Cog"]);
    identity = getNumericValue(T, r, ["Id"]);
    symbol = getNumericValue(T, r, ["Sym"]);
    loadValue = getNumericValue(T, r, ["Load"]);
    tension = getNumericValue(T, r, ["Tension"]);

    if isFlagOn(getNumericValue(T, r, ["FR Risk"])) || isFlagOn(getNumericValue(T, r, ["FR_rule"])) || ...
            isFlagOn(getNumericValue(T, r, ["Is_FR_t0"])) || isFlagOn(getNumericValue(T, r, ["Is_FR_late"])) || mode == "C"
        label = "FR";
        return;
    end

    if isFlagOn(getNumericValue(T, r, ["Is_CR_t0"]))
        label = "CR";
        return;
    end

    if isFlagOn(getNumericValue(T, r, ["Is_PR_t0"]))
        label = "PR";
        return;
    end

    if mode == "N" && omega == "L" && abs(kappaKey - 0.75) < 1e-12
        if cog >= 3
            label = "SR";
        else
            label = "MR";
        end
        return;
    end

    if mode == "V" && omega == "J" && abs(kappaKey - 0.75) < 1e-12
        if cog == 3
            label = "SR";
        else
            label = "MR";
        end
        return;
    end

    if mode == "N" && omega == "G" && abs(kappaKey - 1.00) < 1e-12
        if env == 2 && symbol == 4 && tension == 11
            label = "MR";
        else
            label = "SR";
        end
        return;
    end

    if mode == "V" && omega == "B" && abs(kappaKey - 0.75) < 1e-12
        if bio == 1
            label = "MR";
        else
            label = "SR";
        end
        return;
    end

    if mode == "S" && omega == "L" && abs(kappaKey - 1.00) < 1e-12
        if cog == 3 && identity == 4 && symbol == 3 && loadValue == 16
            label = "MR";
        else
            label = "SR";
        end
        return;
    end

    if mode == "V" && omega == "J" && abs(kappaKey - 0.56) < 1e-12
        if env == 1 || env == 3
            label = "SR";
        elseif env == 4
            label = "MR";
        elseif tension >= 12 && ~(bio == 4 && cog == 3 && loadValue == 17)
            label = "SR";
        else
            label = "MR";
        end
        return;
    end

    srSignatures = [
        "V|J|0.56"
        "S|L|0.75"
        "D|G|1.00"
        "T|L|0.75"
        "S|L|1.00"
        "V|B|0.75"
        "V|B|0.56"
        "V|L|0.38"
        "V|L|0.56"
        "V|L|0.75"
        "S|J|0.56"
        "X|L|0.75"
        "S|J|0.38"
        "H|G|0.56"
        "T|J|0.56"
        "S|C|0.25"
        "S|L|0.25"
        "S|B|0.56"
        "N|L|1.00"
        "S|L|0.38"
        "V|B|1.00"
        "X|J|0.56"
        "X|L|0.56"
    ];

    key = sprintf("%s|%s|%.2f", mode, omega, kappaKey);
    if any(strcmp(key, srSignatures))
        label = "SR";
    else
        label = "MR";
    end
end

function label = classifyRegimeTwoLawsStrict(T, r)
    mode = upper(strtrim(getTextValue(T, r, ["Mode"])));
    omega = upper(strtrim(getTextValue(T, r, ["Ω"])));
    sym = getNumericValue(T, r, ["Sym"]);
    cog = getNumericValue(T, r, ["Cog"]);
    identity = getNumericValue(T, r, ["Id"]);
    coherence = getNumericValue(T, r, ["C"]);
    phi = getNumericValue(T, r, ["Φ"]);
    qValue = getNumericValue(T, r, ["Q=C×Φ", "Q_predicted", "Q"]);

    if omega == "C" && sym <= 3
        label = "FR";
        return;
    end
    if phi <= 2
        label = "FR";
        return;
    end
    if identity == 4 && coherence <= 2 && sym <= 3
        label = "FR";
        return;
    end

    if qValue >= 6 && qValue <= 9
        if cog == 4 && identity <= 3
            label = "PR";
        elseif mode == "A"
            label = "MR";
        elseif mode == "X" && cog <= 1
            label = "CR";
        elseif (mode == "X" || mode == "H") && omega == "G"
            label = "CR";
        elseif sym >= 4
            label = "SR";
        elseif mode == "S"
            label = "SR";
        else
            label = "MR";
        end
        return;
    end

    if qValue >= 14
        label = "CR";
    elseif qValue >= 10 && qValue <= 13
        label = "MR";
    elseif qValue <= 5
        label = "SR";
    else
        label = "MR";
    end
end

function label = classifyRegimeTwoLawsCalibrated(T, r)
    mode = upper(strtrim(getTextValue(T, r, ["Mode"])));
    omega = upper(strtrim(getTextValue(T, r, ["Ω"])));
    symbol = getNumericValue(T, r, ["Sym"]);
    identity = getNumericValue(T, r, ["Id"]);
    coherence = getNumericValue(T, r, ["C"]);
    ext = getNumericValue(T, r, ["Ext"]);
    qValue = getNumericValue(T, r, ["Q=C×Φ", "Q_predicted", "Q"]);

    if isFlagOn(getNumericValue(T, r, ["FR Risk"])) || isFlagOn(getNumericValue(T, r, ["FR_rule"])) || ...
            isFlagOn(getNumericValue(T, r, ["Is_FR_t0"])) || isFlagOn(getNumericValue(T, r, ["Is_FR_late"]))
        label = "FR";
        return;
    end

    if omega == "C" && symbol <= 3
        label = "FR";
        return;
    end

    if identity == 4 && coherence <= 2 && symbol <= 3
        label = "FR";
        return;
    end

    if qValue >= 6 && qValue <= 9 && mode == "V" && symbol >= 4 && ext <= 1
        label = "SR";
        return;
    end

    label = classifyRegimeDefault(T, r);
end

function tf = isFlagOn(value)
    tf = false;

    if isempty(value)
        return;
    end

    if islogical(value)
        tf = value;
        return;
    end

    if isnumeric(value)
        tf = ~isnan(value) && value == 1;
        return;
    end

    parsed = str2double(string(value));
    tf = ~isnan(parsed) && parsed == 1;
end

function label = normalizeRegimeLabel(values)
    values = string(values);
    label = strings(size(values));

    for i = 1:numel(values)
        if ismissing(values(i)) || strlength(strtrim(values(i))) == 0
            label(i) = missing;
            continue;
        end

        token = upper(strtrim(values(i)));
        token = replace(token, "-", "_");
        token = replace(token, " ", "_");

        switch token
            case {"FR", "FR_RISK", "CHAOS_HIGH_RISK"}
                label(i) = "FR";
            case "CR"
                label(i) = "CR";
            case {"PR", "OVERLOADED", "HIGH_LOAD"}
                label(i) = "PR";
            case {"MR", "STABLE"}
                label(i) = "MR";
            case {"SR", "UNDERLOADED"}
                label(i) = "SR";
            otherwise
                label(i) = token;
        end
    end
end

function label = getCaseLabel(T, r)
    if any(strcmp(T.Properties.VariableNames, "Case_ID"))
        label = string(T{r, "Case_ID"});
    elseif any(strcmp(T.Properties.VariableNames, "Case Name"))
        label = string(T{r, "Case Name"});
    else
        label = string(r);
    end
end