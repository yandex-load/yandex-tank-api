app = angular.module("ng-tank-manager", ['ui.ace', 'ui.bootstrap'])

app.constant "TEST_STAGES", ['lock','init','configure','prepare','start','poll','end','postprocess','unlock','finish']
app.constant "_", window._

app.controller "TankManager", ($scope, $interval, $http, TEST_STAGES, _) ->
  $scope.maxProgress = TEST_STAGES.length - 1
  $scope.stages = TEST_STAGES
  updateStatus = () ->
    $http.get("status").success (data) ->
      $scope.status = data
      if $scope.currentSession?
        $scope.sessionStatus = data[$scope.currentSession].current_stage
        $scope.progress = _.indexOf(TEST_STAGES, $scope.sessionStatus)

  $scope.btnDisabled = (stage) ->
    # TODO: fix this!
    btnIdx = _.indexOf(TEST_STAGES, stage)
    ssnIdx = _.indexOf(TEST_STAGES, $scope.sessionStatus)
    brpIdx = _.indexOf(TEST_STAGES, $scope.breakPoint)
    return btnIdx <= ssnIdx or btnIdx < brpIdx

  $scope.runTest = () ->
    $http.post("run", $scope.tankConfig).success (data) ->
      $scope.reply = data
      $scope.currentTest = data.test
      $scope.currentSession = data.session

  $scope.stopTest = () ->
    $http.get("stop?session="+ $scope.currentSession).success (data) ->
      $scope.reply = data

  $interval(updateStatus, 1000)
