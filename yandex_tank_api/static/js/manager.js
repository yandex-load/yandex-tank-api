(function() {
  var app;

  app = angular.module("ng-tank-manager", ['ui.ace', 'ui.bootstrap']);

  app.constant("TEST_STAGES", ['lock', 'init', 'configure', 'prepare', 'start', 'poll', 'end', 'postprocess', 'unlock', 'finish']);

  app.constant("_", window._);

  app.controller("TankManager", function($scope, $interval, $http, TEST_STAGES, _) {
    var updateStatus;
    $scope.maxProgress = TEST_STAGES.length - 1;
    $scope.stages = TEST_STAGES;
    updateStatus = function() {
      return $http.get("status").success(function(data) {
        $scope.status = data;
        if ($scope.currentSession != null) {
          $scope.sessionStatus = data[$scope.currentSession].current_stage;
          return $scope.progress = _.indexOf(TEST_STAGES, $scope.sessionStatus);
        }
      });
    };
    $scope.btnDisabled = function(stage) {
      var brpIdx, btnIdx, ssnIdx;
      btnIdx = _.indexOf(TEST_STAGES, stage);
      ssnIdx = _.indexOf(TEST_STAGES, $scope.sessionStatus);
      brpIdx = _.indexOf(TEST_STAGES, $scope.breakPoint);
      return btnIdx <= ssnIdx || btnIdx < brpIdx;
    };
    $scope.runTest = function() {
      return $http.post("run", $scope.tankConfig).success(function(data) {
        $scope.reply = data;
        $scope.currentTest = data.test;
        return $scope.currentSession = data.session;
      });
    };
    $scope.$watch("breakPoint", function() {
      return $http.post("run?break=" + breakPoint, $scope.tankConfig).success(function(data) {
        $scope.reply = data;
        $scope.currentTest = data.test;
        return $scope.currentSession = data.session;
      });
    });
    $scope.stopTest = function() {
      return $http.get("stop?session=" + $scope.currentSession).success(function(data) {
        return $scope.reply = data;
      });
    };
    return $interval(updateStatus, 1000);
  });

}).call(this);
