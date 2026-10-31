@{
    Severity     = @('Error', 'Warning')
    ExcludeRules = @(
        # Pipeline/bootstrap scripts, not reusable advanced functions.
        'PSUseShouldProcessForStateChangingFunctions'
    )
}
