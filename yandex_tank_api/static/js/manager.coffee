app = angular.module("ng-tank-manager", ['ui.ace', 'ui.bootstrap'])

app.constant "TEST_STAGES", ['lock','init','configure','prepare','start','poll','end','postprocess','unlock','finish']


app.controller "TankManager", ($scope, $interval, $http, TEST_STAGES) ->
  $scope.max_progress = TEST_STAGES.length
  updateStatus = () ->
    $http.get("status").success (data) ->
      $scope.status = data
      if $scope.current_session?
        $scope.session_status = data[$scope.current_session].current_stage
        $scope.progress = _.indexOf(TEST_STAGES, $scope.session_status)

  $scope.runTest = () ->
    $http.post("run", $scope.tankConfig).success (data) ->
      $scope.reply = data
      $scope.current_test = data.test
      $scope.current_session = data.session

  $scope.stopTest = () ->
    $http.get("stop?session="+ $scope.current_session).success (data) ->
      $scope.reply = data

  $interval(updateStatus, 1000)
